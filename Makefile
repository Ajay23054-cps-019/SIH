CXX = g++
CXXFLAGS = -std=c++17 -O2 -Wall -Wextra -pedantic
LDFLAGS =

TARGET = shm_writer

all: $(TARGET)

$(TARGET): shm_writer.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)

.PHONY: all clean
