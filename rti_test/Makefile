NDDSHOME ?= /Applications/rti_connext_dds-7.3.0
ARCH ?= arm64Darwin20clang12.0

CC = clang
CFLAGS = -I$(NDDSHOME)/include -I$(NDDSHOME)/include/ndds -DRTI_UNIX -DRTI_DARWIN
LDFLAGS = -L$(NDDSHOME)/lib/$(ARCH) -Wl,-rpath,$(NDDSHOME)/lib/$(ARCH)
LIBS = -lnddsc -lnddscore -ldl -lm -lpthread

# Static type sources
STATIC_SRCS = SimpleType.c SimpleTypePlugin.c SimpleTypeSupport.c

all: simple_pub static_pub static_sub

simple_pub: simple_pub.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS) $(LIBS)

static_pub: SimpleType_publisher.c $(STATIC_SRCS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LIBS)

static_sub: SimpleType_subscriber.c $(STATIC_SRCS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LIBS)

clean:
	rm -f simple_pub static_pub static_sub

.PHONY: all clean
