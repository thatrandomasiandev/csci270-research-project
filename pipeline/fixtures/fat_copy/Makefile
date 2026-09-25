CC ?= cc
CFLAGS ?= -O2

.PHONY: stock opt clean all

all: stock opt

stock: stock.c
	$(CC) $(CFLAGS) -o stock stock.c

opt: opt.c
	$(CC) $(CFLAGS) -o opt opt.c

clean:
	rm -f stock opt
