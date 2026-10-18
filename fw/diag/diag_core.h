/* Passive C2M diagnostics: portable, bounded parsing helpers. */
#ifndef DIAG_CORE_H
#define DIAG_CORE_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <limits.h>
#define DIAG_CAP 15000u
#define DIAG_SLOT_BYTES (8u * 1024u * 1024u)
#define DIAG_MAGIC "C2M_DIAG_V1\n"
struct linebuf { char s[DIAG_CAP]; size_t n; int truncated; };
static void add(struct linebuf *b, const char *fmt, ...) {
    int n; va_list ap;
    if (b->truncated) return;
    va_start(ap, fmt); n = vsnprintf(b->s+b->n, sizeof(b->s)-b->n, fmt, ap); va_end(ap);
    if (n < 0 || (size_t)n >= sizeof(b->s)-b->n) { b->truncated=1; return; }
    b->n += (size_t)n;
}
static uint32_t crc32_bytes(const void *data, size_t n) {
    const unsigned char *p=data; uint32_t c=UINT32_MAX; size_t i; unsigned j;
    for (i=0;i<n;i++) { c^=p[i]; for(j=0;j<8;j++) c=(c>>1)^((0u-(c&1u))&0xedb88320u); }
    return ~c;
}
static int number(const char *s, unsigned long long *v) {
    char *e; const char *p=s;
    if (!*s) return 0;
    while (*p) { if (*p<'0'||*p>'9') return 0; p++; }
    errno=0; *v=strtoull(s,&e,10); return !errno && !*e;
}
struct procinfo { unsigned long long ppid,utime,stime,start,rss; char state; };
/* ')' may occur in comm. Fields 3..24 follow its FINAL ')'. */
static int parse_stat(char *s, struct procinfo *p) {
    char *q=strrchr(s,')'), *end; int f; unsigned long long v;
    memset(p,0,sizeof(*p));
    if (!q || q[1]!=' ' || !q[2] || q[3]!=' ') return 0;
    p->state=q[2]; q+=4;
    for(f=4;f<=24;f++) {
        char save; while(*q==' ') q++; if(!*q) return 0;
        end=q; while(*end && *end!=' ' && *end!='\n') end++;
        save=*end; *end=0;
        if(f==4||f==14||f==15||f==22||f==24) {
            if(!number(q,&v)) { *end=save; return 0; }
            if(f==4)p->ppid=v; if(f==14)p->utime=v; if(f==15)p->stime=v;
            if(f==22)p->start=v; if(f==24)p->rss=v;
        }
        *end=save; q=end;
    }
    return 1;
}
static int calib_state(const char *s) {
    const char *p=s; int result=0,seen=0;
    while(*p) {
        const char *e=strchr(p,'\n'); size_t n=e?(size_t)(e-p):strlen(p);
        if(n==23 && (!memcmp(p,"--install_calib_state=1",23) || !memcmp(p,"--install_calib_state=2",23))) {
            /* Exact whole line only; no substring acceptance. */
            result=p[n-1]-'0'; seen++;
        }
        if(!e) break; p=e+1;
    }
    return seen==1?result:0;
}
static const char *proc_name(const char *comm) {
    static const char *const names[]={"adas","lane_accelerator","lane_postprocess","mutualism","cardv","c2m-idle","c2m-signs","c2m-debug","c2m-web","c2m-wifi","dropbear","goahead",NULL};
    unsigned i; for(i=0;names[i];i++) {
        size_t n=strlen(names[i]); if(n>15)n=15;
        if(strlen(comm)==n && !memcmp(comm,names[i],n))return names[i];
    } return NULL;
}
static int enum_value(const char *s,const char *options) {
    const char *p=options; size_t n=strlen(s);
    while(*p) { const char *e=strchr(p,'|'); size_t z=e?(size_t)(e-p):strlen(p);
        if(n==z&&!memcmp(p,s,n))return 1; if(!e)break; p=e+1; }
    return 0;
}
/* Only known key/value pairs reach output. No arbitrary strings, SSIDs, IPs,
 * keys, GPS measurements or config contents can escape through this path. */
static void safe_status(struct linebuf *b, const char *label, char *text, int kind) {
    char *p=text; unsigned lines=0;
    while(*p && lines++<64) {
        char *e=strchr(p,'\n'), *eq; unsigned long long v;
        if(e)*e=0; eq=strchr(p,'=');
        if(eq) { const char *opts=NULL; int numeric=0; *eq++=0;
            if(kind==0) {
                if(!strcmp(p,"state"))opts="waiting_gps|warming_up|ready|stale|no_database|disabled|error";
                if(!strcmp(p,"gps_fresh")||!strcmp(p,"active"))opts="0|1";
                if(!strcmp(p,"sequence"))numeric=1;
            } else if(kind==1) {
                if(!strcmp(p,"state"))opts="inactive|starting|active|expired|error|stopped|listening|failed";
                if(!strcmp(p,"lifetime"))opts="boot|window";
                if(!strcmp(p,"window_sec"))numeric=1;
            } else {
                if(!strcmp(p,"sta_state"))opts="unknown|idle|disconnected|connecting|associating|connected|associated_no_ip|stopped|failed|unsupported";
                if(!strcmp(p,"sta_supported"))opts="yes|no|unknown|0|1";
                if(!strcmp(p,"bt_presence"))opts="present|absent|unknown";
                if(!strcmp(p,"dhcp_helper"))opts="missing|available";
            }
            if((opts&&enum_value(eq,opts))||(numeric&&number(eq,&v)&&v<=UINT32_MAX)) add(b," %s.%s=%s",label,p,eq);
        }
        if(!e)break; p=e+1;
    }
}
static int mount_line(const char *s) {
    char dev[80],path[80],fs[40],opts[256];
    if(sscanf(s,"%79s %79s %39s %255s",dev,path,fs,opts)!=4)return 0;
    if(strcmp(path,"/mnt/mmc") || (strcmp(dev,"/dev/mmcblk0")&&strcmp(dev,"/dev/mmcblk0p1")))return 0;
    return !strncmp(opts,"rw,",3)||!strcmp(opts,"rw");
}
static int needs_rotation(unsigned long long size,size_t n) {
    return size>DIAG_SLOT_BYTES || n>DIAG_SLOT_BYTES || size>DIAG_SLOT_BYTES-n;
}
#endif
