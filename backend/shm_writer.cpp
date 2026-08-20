#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cstdint>
#include <cstring>
#include <atomic>
#include <chrono>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <set>
#include <algorithm>
#include <dirent.h>
#include <poll.h>

constexpr uint64_t SHM_MAGIC = 0x534D4F4E4E4F4D53ULL;
constexpr uint64_t SHM_VERSION = 1;
constexpr uint64_t SLOT_SIZE = 4096;
constexpr uint64_t SLOT_COUNT = 256;
constexpr uint64_t SHM_SIZE = 32 + SLOT_COUNT * SLOT_SIZE;
constexpr const char* SHM_NAME = "/sysmon_shm";
constexpr int WRITE_INTERVAL_MS = 100;
constexpr int MAX_PROCESSES = 24;
constexpr int MAX_NAME_LEN = 64;

struct ProcessInfo {
    int32_t pid;
    char name[MAX_NAME_LEN];
    float cpu_percent;
    float memory_percent;
    uint32_t reserved;
};

struct alignas(8) MetricsSlot {
    uint64_t timestamp_ns;
    double cpu_percent;
    uint64_t ram_used;
    uint64_t ram_total;
    double ram_percent;
    uint64_t bytes_sent;
    uint64_t bytes_received;
    uint32_t process_count;
    uint32_t reserved;
    ProcessInfo processes[MAX_PROCESSES];
};

struct alignas(8) ShmHeader {
    uint64_t magic;
    uint64_t version;
    uint64_t write_index;
    uint64_t slot_size;
    uint64_t slot_count;
};

static std::set<std::string> g_targets = {"code", "chrome", "firefox"};
static uint64_t g_prev_cpu_total = 0;
static uint64_t g_prev_cpu_idle = 0;
static uint64_t g_prev_bytes_sent = 0;
static uint64_t g_prev_bytes_recv = 0;

static std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> parts;
    std::stringstream ss(s);
    std::string item;
    while (std::getline(ss, item, delim)) {
        size_t start = item.find_first_not_of(" \t\r\n");
        size_t end = item.find_last_not_of(" \t\r\n");
        if (start == std::string::npos || end == std::string::npos) continue;
        parts.push_back(item.substr(start, end - start + 1));
    }
    return parts;
}

static double read_cpu_percent() {
    std::ifstream f("/proc/stat");
    if (!f) return 0.0;
    std::string line;
    std::getline(f, line);
    auto parts = split(line, ' ');
    if (parts.size() < 8) return 0.0;
    uint64_t user = std::stoull(parts[1]);
    uint64_t nice = std::stoull(parts[2]);
    uint64_t system = std::stoull(parts[3]);
    uint64_t idle = std::stoull(parts[4]);
    uint64_t iowait = std::stoull(parts[5]);
    uint64_t irq = std::stoull(parts[6]);
    uint64_t softirq = std::stoull(parts[7]);
    uint64_t total = user + nice + system + idle + iowait + irq + softirq;
    uint64_t idle_total = idle + iowait;
    double percent = 0.0;
    if (g_prev_cpu_total != 0) {
        uint64_t total_delta = total - g_prev_cpu_total;
        uint64_t idle_delta = idle_total - g_prev_cpu_idle;
        if (total_delta > 0) {
            percent = (1.0 - (double)idle_delta / (double)total_delta) * 100.0;
        }
    }
    g_prev_cpu_total = total;
    g_prev_cpu_idle = idle_total;
    return percent;
}

static std::pair<uint64_t, uint64_t> read_memory() {
    std::ifstream f("/proc/meminfo");
    if (!f) return {0, 0};
    std::string line;
    uint64_t total = 0, available = 0;
    while (std::getline(f, line)) {
        auto parts = split(line, ' ');
        if (parts.size() < 2) continue;
        if (parts[0] == "MemTotal:") total = std::stoull(parts[1]) * 1024;
        if (parts[0] == "MemAvailable:") available = std::stoull(parts[1]) * 1024;
    }
    return {total - available, total};
}

static std::pair<uint64_t, uint64_t> read_network() {
    std::ifstream f("/proc/net/dev");
    if (!f) return {0, 0};
    std::string line;
    uint64_t total_sent = 0, total_recv = 0;
    while (std::getline(f, line)) {
        if (line.find(':') == std::string::npos) continue;
        auto pos = line.find(':');
        std::string iface = line.substr(0, pos);
        std::string data = line.substr(pos + 1);
        auto parts = split(data, ' ');
        if (parts.size() < 10) continue;
        size_t start = iface.find_first_not_of(" \t\r\n");
        size_t end = iface.find_last_not_of(" \t\r\n");
        std::string iface_trimmed = (start == std::string::npos || end == std::string::npos) ? "" : iface.substr(start, end - start + 1);
        if (iface_trimmed == "lo") continue;
        total_recv += std::stoull(parts[0]);
        total_sent += std::stoull(parts[8]);
    }
    uint64_t sent = 0, recv = 0;
    if (g_prev_bytes_sent != 0) {
        sent = total_sent > g_prev_bytes_sent ? total_sent - g_prev_bytes_sent : 0;
        recv = total_recv > g_prev_bytes_recv ? total_recv - g_prev_bytes_recv : 0;
    }
    g_prev_bytes_sent = total_sent;
    g_prev_bytes_recv = total_recv;
    return {sent, recv};
}

static std::string read_process_name(pid_t pid) {
    char path[256];
    snprintf(path, sizeof(path), "/proc/%d/comm", pid);
    std::ifstream f(path);
    if (!f) return "";
    std::string name;
    std::getline(f, name);
    return name;
}

static std::pair<float, float> read_process_stats(pid_t pid) {
    char path[256];
    snprintf(path, sizeof(path), "/proc/%d/stat", pid);
    std::ifstream f(path);
    if (!f) return {0.0f, 0.0f};
    std::string line;
    std::getline(f, line);
    size_t start = line.find('(');
    size_t end = line.rfind(')');
    if (start == std::string::npos || end == std::string::npos) return {0.0f, 0.0f};
    std::vector<std::string> parts;
    std::stringstream ss(line.substr(end + 2));
    std::string item;
    while (std::getline(ss, item, ' ')) parts.push_back(item);
    if (parts.size() < 22) return {0.0f, 0.0f};
    long long rss = std::stoll(parts[21]);
    long long page_size = sysconf(_SC_PAGE_SIZE);
    float cpu = 0.0f;
    float mem = 0.0f;
    {
        std::ifstream mf("/proc/meminfo");
        if (mf) {
            std::string ml;
            while (std::getline(mf, ml)) {
                auto mp = split(ml, ' ');
                if (mp.size() >= 2 && mp[0] == "MemTotal:") {
                    mem = (float)rss * page_size / (std::stoull(mp[1]) * 1024) * 100.0f;
                    break;
                }
            }
        }
    }
    return {cpu, mem};
}

static std::vector<ProcessInfo> read_target_processes() {
    std::vector<ProcessInfo> result;
    DIR* dir = opendir("/proc");
    if (!dir) return result;
    struct dirent* ent;
    while ((ent = readdir(dir)) != nullptr) {
        if (ent->d_type != DT_DIR) continue;
        char* end;
        long pid = strtol(ent->d_name, &end, 10);
        if (*end != '\0' || pid <= 0) continue;
        std::string name = read_process_name(pid);
        if (name.empty()) continue;
        std::string name_lower = name;
        std::transform(name_lower.begin(), name_lower.end(), name_lower.begin(), ::tolower);
        bool matched = false;
        for (const auto& t : g_targets) {
            if (name_lower.find(t) != std::string::npos) {
                matched = true;
                break;
            }
        }
        if (!matched) continue;
        auto [cpu, mem] = read_process_stats(pid);
        ProcessInfo pi{};
        pi.pid = (int32_t)pid;
        snprintf(pi.name, MAX_NAME_LEN, "%s", name.c_str());
        pi.cpu_percent = cpu;
        pi.memory_percent = mem;
        result.push_back(pi);
        if ((int)result.size() >= MAX_PROCESSES) break;
    }
    closedir(dir);
    std::sort(result.begin(), result.end(), [](const ProcessInfo& a, const ProcessInfo& b) {
        return a.cpu_percent > b.cpu_percent;
    });
    return result;
}

int main() {
    shm_unlink(SHM_NAME);
    int fd = shm_open(SHM_NAME, O_CREAT | O_RDWR, 0666);
    if (fd < 0) {
        perror("shm_open");
        return 1;
    }
    if (ftruncate(fd, SHM_SIZE) < 0) {
        perror("ftruncate");
        close(fd);
        return 1;
    }
    void* addr = mmap(nullptr, SHM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (addr == MAP_FAILED) {
        perror("mmap");
        close(fd);
        return 1;
    }
    close(fd);

    ShmHeader* header = static_cast<ShmHeader*>(addr);
    header->magic = SHM_MAGIC;
    header->version = SHM_VERSION;
    header->write_index = 0;
    header->slot_size = SLOT_SIZE;
    header->slot_count = SLOT_COUNT;

    uint8_t* slots = static_cast<uint8_t*>(addr) + sizeof(ShmHeader);

    while (true) {
        uint64_t idx = header->write_index;
        uint8_t* slot_ptr = slots + (idx % SLOT_COUNT) * SLOT_SIZE;
        MetricsSlot* slot = reinterpret_cast<MetricsSlot*>(slot_ptr);

        auto now = std::chrono::high_resolution_clock::now();
        slot->timestamp_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            now.time_since_epoch()).count();
        slot->cpu_percent = read_cpu_percent();
        auto [used, total] = read_memory();
        slot->ram_used = used;
        slot->ram_total = total;
        slot->ram_percent = total > 0 ? (double)used / (double)total * 100.0 : 0.0;
        auto [sent, recv] = read_network();
        slot->bytes_sent = sent;
        slot->bytes_received = recv;

        auto procs = read_target_processes();
        slot->process_count = std::min((uint32_t)procs.size(), (uint32_t)MAX_PROCESSES);
        for (uint32_t i = 0; i < slot->process_count; ++i) {
            slot->processes[i] = procs[i];
        }

        header->write_index = idx + 1;
        usleep(WRITE_INTERVAL_MS * 1000);
    }

    munmap(addr, SHM_SIZE);
    return 0;
}
