# Compiler settings
CC = gcc
CXX = g++
JAVAC = javac
JAVA = java
PYTHON = python3

# PostgreSQL paths
CFLAGS = -I/usr/include/postgresql
CPPFLAGS = -lpqxx
LDFLAGS = -lpq
JAR_PATH = /usr/share/java/postgresql.jar

# Source files
C_SRC = 22CS30027A3.c
CPP_SRC = 22CS30027A3.cpp
JAVA_SRC = Query.java
PYTHON_SRC = 22CS30027A3.py

# Executables
C_EXEC = 22CS30027A3c.out
CPP_EXEC = 22CS30027A3cpp.out
JAVA_CLASS = Query.class

# Default target
all: $(C_EXEC) $(CPP_EXEC) $(JAVA_CLASS)

# Compile C program
$(C_EXEC): $(C_SRC)
	$(CC) -o $(C_EXEC) $(C_SRC) $(CFLAGS) $(LDFLAGS)

# Compile C++ program
$(CPP_EXEC): $(CPP_SRC)
	$(CXX) -o $(CPP_EXEC) $(CPP_SRC) $(CPPFLAGS) $(LDFLAGS)

# Compile Java program
$(JAVA_CLASS): $(JAVA_SRC)
	$(JAVAC) -cp .:$(JAR_PATH) $(JAVA_SRC)

# Run C program
run_c: $(C_EXEC)
	./$(C_EXEC)

# Run C++ program
run_cpp: $(CPP_EXEC)
	./$(CPP_EXEC)

# Run Java program
run_java: $(JAVA_CLASS)
	$(JAVA) -cp .:$(JAR_PATH) Query

# Run Python program
run_py:
	$(PYTHON) $(PYTHON_SRC)

# Clean compiled files
clean:
	rm -f $(C_EXEC) $(CPP_EXEC) $(JAVA_CLASS) *.out
