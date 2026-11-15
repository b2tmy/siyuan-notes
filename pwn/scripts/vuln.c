// 栈溢出靶子：read 读 0x100 进 32 字节缓冲区
// gcc -O0 -fno-stack-protector -no-pie -z execstack -o vuln vuln.c
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

void win(void) {
    system("/bin/sh");
}

int main(void) {
    char buf[32];
    puts("input:");
    read(0, buf, 0x100);
    puts("bye");
    return 0;
}
