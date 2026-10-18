/* C2M continuous diagnostics v1. Passive reads; only this logger's namespace
 * is writable. No sockets, subprocesses, IPC, control operations or raw GPS.
 * SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "diag_core.h"
#include <unistd.h>
#include <fcntl.h>
#include <dirent.h>
#include <signal.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/file.h>
#include <sys/klog.h>
#include <sys/sysmacros.h>
#define CARD "/mnt/mmc/C2M_DIAG/continuous"
#define RAM "/tmp/c2m-continuous-diag"
#define MAXPROC 128
static volatile sig_atomic_t stopping;
static void stop_handler(int sig) { (void)sig; stopping=1; }
static int plain(int fd) { struct stat s; return fstat(fd,&s)==0 && S_ISREG(s.st_mode) && s.st_nlink==1; }
/* Anchored directory descent: every component opened O_NOFOLLOW, not merely
 * lstat before an unsafe open. No '.', '..', empty or relative components. */
static int directory(const char *path) {
    char copy[512],*p; int fd,n;
    if(path[0]!='/'||strlen(path)>=sizeof(copy))return -1;
    strcpy(copy,path+1); fd=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC); if(fd<0)return -1;
    p=copy; while(*p) { char *q=strchr(p,'/'); if(q)*q=0;
        if(!*p||!strcmp(p,".")||!strcmp(p,"..")) { close(fd);return -1; }
        n=openat(fd,p,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);close(fd);if(n<0)return -1;fd=n;
        if(!q)break;p=q+1;if(!*p){close(fd);return -1;}
    } return fd;
}
static int read_at(int dir,const char *name,char *buf,size_t cap) {
    int fd=openat(dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK); ssize_t n; size_t used=0;
    if(fd<0)return -1;
    if(!plain(fd)){close(fd);return -1;}
    while(used<cap-1) { n=read(fd,buf+used,cap-1-used); if(n<0&&errno==EINTR)continue;
        if(n<0){close(fd);return -1;}if(!n)break;used+=(size_t)n; }
    /* Oversize data rejected, never silently hash a prefix. */
    if(used==cap-1) { char c; n=read(fd,&c,1);if(n!=0){close(fd);return -1;} }
    close(fd);buf[used]=0;return (int)used;
}
static int read_path(const char *path,char *buf,size_t cap) {
    char copy[512],*p;int dir,n;if(strlen(path)>=sizeof(copy))return -1;
    strcpy(copy,path);p=strrchr(copy,'/');if(!p||!p[1])return -1;*p++=0;
    dir=directory(copy);if(dir<0)return -1;n=read_at(dir,p,buf,cap);close(dir);return n;
}
static int write_all(int fd,const char *s,size_t n) {
    while(n) { ssize_t k=write(fd,s,n);if(k<0&&errno==EINTR)continue;if(k<=0)return -1;s+=k;n-=(size_t)k; }return 0;
}
static int owned_dir(int parent,const char *name,int private_dir) {
    int fd;struct stat s;
    if(mkdirat(parent,name,private_dir?0700:0755)<0&&errno!=EEXIST)return -1;
    fd=openat(parent,name,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;
    if(fstat(fd,&s)<0||s.st_uid!=geteuid()||(private_dir&&(s.st_mode&0777)!=0700)) {close(fd);return -1;}
    return fd;
}
static int ram_setup(int *lockfd) {
    int tmp=directory("/tmp"),d,fd;struct stat s;
    if(tmp<0)return -1;d=owned_dir(tmp,"c2m-continuous-diag",1);close(tmp);if(d<0)return -1;
    fd=openat(d,"lock",O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0600);
    if(fd<0||!plain(fd)||fstat(fd,&s)<0||s.st_uid!=geteuid()||(s.st_mode&0777)!=0600||flock(fd,LOCK_EX|LOCK_NB)<0) {
        if(fd>=0)close(fd);close(d);return -1;
    }*lockfd=fd;return d;
}
/* /proc/mounts is normally a symlink to self/mounts. Use numeric self PID
 * instead, preserving no-symlink checks for all actual opens. */
static int valid_mount(void) {
    char path[80],buf[16384],*p;int found=0;struct stat a,b;
    snprintf(path,sizeof(path),"/proc/%ld/mounts",(long)getpid());
    if(read_path(path,buf,sizeof(buf))<0)return 0;
    p=buf;while(*p){char *e=strchr(p,'\n');if(e)*e=0;if(mount_line(p)) {
        char dev[80];if(sscanf(p,"%79s",dev)==1 && lstat(dev,&a)==0 && S_ISBLK(a.st_mode) && lstat("/mnt/mmc",&b)==0 && S_ISDIR(b.st_mode) && a.st_rdev==b.st_dev)found++;
    }if(!e)break;p=e+1;}return found==1;
}
static int slot_name(const char *n) {
    int i;char s[32];if(!strcmp(n,"current.log"))return 1;
    for(i=1;i<=15;i++){snprintf(s,sizeof(s),"log%02d.log",i);if(!strcmp(s,n))return 1;}return 0;
}
static int log_header(int dir,const char *name) {
    char s[sizeof(DIAG_MAGIC)];int fd=openat(dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);ssize_t n;struct stat st;
    if(fd<0)return errno==ENOENT?0:-1;
    if(!plain(fd)||fstat(fd,&st)<0||st.st_size>DIAG_SLOT_BYTES){close(fd);return -1;}
    n=read(fd,s,sizeof(DIAG_MAGIC)-1);close(fd);
    return n==(ssize_t)(sizeof(DIAG_MAGIC)-1)&&!memcmp(s,DIAG_MAGIC,sizeof(DIAG_MAGIC)-1)?1:-1;
}
static int namespace_ok(int dir) {
    int copy=dup(dir),bad=0,marker=0,entries=0;DIR *dp;struct dirent *de;char buf[80];
    if(copy<0)return 0;dp=fdopendir(copy);if(!dp){close(copy);return 0;}
    for(;;) {errno=0;de=readdir(dp);if(!de){if(errno)bad=1;break;}
        if(!strcmp(de->d_name,".")||!strcmp(de->d_name,".."))continue;entries++;
        if(!strcmp(de->d_name,"owner.v1"))marker=1;
        else if(!slot_name(de->d_name)||log_header(dir,de->d_name)!=1)bad=1;
    }closedir(dp);if(bad)return 0;
    if(!marker) {int fd;if(entries)return 0;
        fd=openat(dir,"owner.v1",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)return 0;
        bad=write_all(fd,DIAG_MAGIC,sizeof(DIAG_MAGIC)-1);if(!bad)bad=fsync(fd);close(fd);return !bad;
    }
    return read_at(dir,"owner.v1",buf,sizeof(buf))==(int)(sizeof(DIAG_MAGIC)-1)&&!strcmp(buf,DIAG_MAGIC);
}
static int rotate(int dir) {
    int i;char a[32],b[32];
    /* namespace_ok has validated ALL fixed files first. No foreign deletion. */
    if(unlinkat(dir,"log15.log",0)<0&&errno!=ENOENT)return -1;
    for(i=14;i>=1;i--){snprintf(a,sizeof(a),"log%02d.log",i);snprintf(b,sizeof(b),"log%02d.log",i+1);
        if(renameat(dir,a,dir,b)<0&&errno!=ENOENT)return -1;}
    return renameat(dir,"current.log",dir,"log01.log");
}
static int append_sample(struct linebuf *b,int event,long long mono) {
    int base=-1,top=-1,dir=-1,fd=-1,rc=1;struct statvfs v;struct stat st;static long long last_sync=-60000;
    if(!valid_mount())return 1;
    base=directory("/mnt/mmc");if(base<0)goto out;
    if(fstatvfs(base,&v)<0||(unsigned long long)v.f_bavail*v.f_frsize<32ull*1024*1024) {rc=2;goto out;}
    top=owned_dir(base,"C2M_DIAG",0);if(top<0)goto out;
    dir=owned_dir(top,"continuous",0);if(dir<0||!namespace_ok(dir)){rc=3;goto out;}
    if(!valid_mount()){rc=1;goto out;}
    fd=openat(dir,"current.log",O_WRONLY|O_APPEND|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
    if(fd<0&&errno==ENOENT) {
new_file:
        fd=openat(dir,"current.log",O_WRONLY|O_CREAT|O_EXCL|O_APPEND|O_CLOEXEC|O_NOFOLLOW,0600);
        if(fd<0)goto out;if(write_all(fd,DIAG_MAGIC,sizeof(DIAG_MAGIC)-1)<0)goto out;
    }
    if(fd<0||!plain(fd)||fstat(fd,&st)<0)goto out;
    if(needs_rotation((unsigned long long)st.st_size,b->n)) {
        close(fd);fd=-1;if(rotate(dir)<0)goto out;goto new_file;
    }
    if(write_all(fd,b->s,b->n)<0){rc=4;goto out;}rc=0;
    if(event||mono-last_sync>=60000) {if(fsync(fd)<0)rc=4;else last_sync=mono;}
out:
    if(fd>=0)close(fd);if(dir>=0)close(dir);if(top>=0)close(top);if(base>=0)close(base);return rc;
}
static void status_write(int dir,unsigned long long seq,long long mono,int rc,int truncated) {
    char s[256];int fd,n;struct stat st;
    if(fstatat(dir,"status.new",&st,AT_SYMLINK_NOFOLLOW)==0)return; /* don't overwrite foreign stale file */
    fd=openat(dir,"status.new",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)return;
    n=snprintf(s,sizeof(s),"version=1\npid=%ld\nsample=%llu\nmonotonic_ms=%lld\ncard_result=%d\ntruncated=%d\nstate=%s\n",(long)getpid(),seq,mono,rc,truncated,stopping?"stopped":"running");
    if(write_all(fd,s,(size_t)n)==0) {
        if(fstatat(dir,"status",&st,AT_SYMLINK_NOFOLLOW)<0 ? errno==ENOENT : S_ISREG(st.st_mode)&&st.st_nlink==1&&st.st_uid==geteuid()) (void)renameat(dir,"status.new",dir,"status");
    }close(fd);(void)unlinkat(dir,"status.new",0);
}
struct tracked { unsigned pid; unsigned long long start,rss_peak,fd_peak; int seen; };
static struct tracked tracks[MAXPROC];
static void processes(struct linebuf *b,int *event) {
    DIR *dp=opendir("/proc");struct dirent *de;unsigned scanned=0,matched=0,lost=0;size_t i;
    for(i=0;i<MAXPROC;i++)tracks[i].seen=0;if(!dp){add(b," proc_error=1");return;}
    while((de=readdir(dp))&&scanned++<4096) {
        unsigned long long pid;char path[96],buf[8192],comm[80];const char *name;int d,fdcount=0,threads=-1;unsigned long long vmrss=0;struct procinfo p;struct tracked *t=NULL;
        if(!number(de->d_name,&pid)||pid>INT_MAX)continue;
        snprintf(path,sizeof(path),"/proc/%llu",pid);d=directory(path);if(d<0)continue;
        if(read_at(d,"comm",comm,sizeof(comm))<0){close(d);continue;}comm[strcspn(comm,"\n")]=0;name=proc_name(comm);
        if(!name||read_at(d,"stat",buf,sizeof(buf))<0||!parse_stat(buf,&p)||!strchr("RSDZTtWXxKPI",p.state)){close(d);continue;}
        matched++;for(i=0;i<MAXPROC;i++)if(tracks[i].pid==pid&&tracks[i].start==p.start){t=&tracks[i];break;}
        if(!t){for(i=0;i<MAXPROC;i++)if(!tracks[i].pid){t=&tracks[i];break;}*event=1;}
        if(t){if(!t->pid){t->pid=(unsigned)pid;t->start=p.start;add(b," appeared=%u/%llu",t->pid,t->start);}t->seen=1;if(p.rss>t->rss_peak)t->rss_peak=p.rss;}
        if(read_at(d,"status",buf,sizeof(buf))>=0){char *q=buf;while(*q){char *e=strchr(q,'\n');if(e)*e=0;
            if(!strncmp(q,"VmRSS:",6)) (void)sscanf(q+6,"%llu",&vmrss);
            if(!strncmp(q,"Threads:",8)) (void)sscanf(q+8,"%d",&threads);
            if(!e)break;q=e+1;}}
        {int f=openat(d,"fd",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);DIR *fds=f<0?NULL:fdopendir(f);struct dirent *ent;
            if(fds){while((ent=readdir(fds))&&fdcount<4096)if(ent->d_name[0]!='.')fdcount++;closedir(fds);}else {if(f>=0)close(f);fdcount=-1;}}
        if(t&&fdcount>0&&(unsigned)fdcount>t->fd_peak)t->fd_peak=(unsigned)fdcount;
        add(b," p=%s,%llu,%llu,%c,%llu,%llu,%llu,%llu,%llu,%d,%d,%llu,%llu",name,pid,p.ppid,p.state,p.start,p.utime,p.stime,p.rss,vmrss,threads,fdcount,t?t->rss_peak:0,t?t->fd_peak:0);
        close(d);
    }closedir(dp);for(i=0;i<MAXPROC;i++)if(tracks[i].pid&&!tracks[i].seen){add(b," disappeared=%u/%llu",tracks[i].pid,tracks[i].start);memset(&tracks[i],0,sizeof(tracks[i]));lost++;*event=1;}
    add(b," proc_count=%u proc_lost=%u proc_scan_capped=%d",matched,lost,scanned>=4096);
}
static void resources(struct linebuf *b) {
    char buf[32768],path[80],*p;static unsigned long long used_peak;unsigned long long total=0,avail=0;
    if(read_path("/proc/meminfo",buf,sizeof(buf))>=0){p=buf;while(*p){char *e=strchr(p,'\n');if(e)*e=0;
        static const char *const keys[]={"MemTotal","MemFree","MemAvailable","Buffers","Cached","SwapTotal","SwapFree","Slab",NULL};unsigned i;
        for(i=0;keys[i];i++) {size_t n=strlen(keys[i]);unsigned long long v;if(!strncmp(p,keys[i],n)&&p[n]==':'&&sscanf(p+n+1,"%llu",&v)==1){add(b," mem.%s=%llu",keys[i],v);if(i==0)total=v;if(i==2)avail=v;}}
        if(!e)break;p=e+1;}if(avail&&total>=avail&&total-avail>used_peak)used_peak=total-avail;add(b," mem.used_peak_kb=%llu",used_peak);}
    if(read_path("/proc/loadavg",buf,sizeof(buf))>=0){double a,c,d;if(sscanf(buf,"%lf %lf %lf",&a,&c,&d)==3&&a>=0&&a<100000&&c>=0&&c<100000&&d>=0&&d<100000)add(b," load=%.2f,%.2f,%.2f",a,c,d);}
    if(read_path("/proc/stat",buf,sizeof(buf))>=0){unsigned long long a[8];if(sscanf(buf,"cpu %llu %llu %llu %llu %llu %llu %llu %llu",a,a+1,a+2,a+3,a+4,a+5,a+6,a+7)==8)add(b," cpu=%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu",a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7]);}
    snprintf(path,sizeof(path),"/proc/%ld/net/dev",(long)getpid());
    if(read_path(path,buf,sizeof(buf))>=0){p=buf;while(*p){char *e=strchr(p,'\n'),ifname[32];unsigned long long a[16];unsigned i;if(e)*e=0;
        char *colon=strchr(p,':');if(colon){*colon=0;if(sscanf(p,"%31s",ifname)==1&&(!strcmp(ifname,"wlan0")||!strcmp(ifname,"wlan1"))){char *q=colon+1;int ok=1;for(i=0;i<16;i++){char *end;while(*q==' ')q++;errno=0;a[i]=strtoull(q,&end,10);if(end==q||errno){ok=0;break;}q=end;}if(ok)add(b," net.%s=%llu,%llu,%llu,%llu,%llu,%llu",ifname,a[0],a[2],a[3],a[8],a[10],a[11]);}}
        if(!e)break;p=e+1;}}
    /* Stream /proc TCP tables, bounded to 8192 rows per family. Addresses
     * are only skipped in memory and NEVER written or parsed for output. */
    {const unsigned ports[]={80,8080,24012,26012,2222};unsigned counts[5][2]={{0}},family;int capped=0;
        for(family=0;family<2;family++){int d,fd;FILE *f;unsigned rows=0;char name[16];snprintf(path,sizeof(path),"/proc/%ld/net",(long)getpid());d=directory(path);if(d<0)continue;snprintf(name,sizeof(name),"%s",family?"tcp6":"tcp");fd=openat(d,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);close(d);if(fd<0)continue;if(!plain(fd)){close(fd);continue;}f=fdopen(fd,"r");if(!f){close(fd);continue;}
            while(fgets(buf,1024,f)&&rows++<8192){unsigned local,state,i;/* local address width up to 32 hex */
                if(sscanf(buf," %*u: %*32[0123456789ABCDEFabcdef]:%x %*32[0123456789ABCDEFabcdef]:%*x %x",&local,&state)==2)for(i=0;i<5;i++)if(local==ports[i]){if(state==1)counts[i][0]++;if(state==10)counts[i][1]++;}}
            if(rows>=8192)capped=1;fclose(f);}
        for(family=0;family<5;family++)add(b," tcp.%u=%u,%u",ports[family],counts[family][0],counts[family][1]);add(b," tcp_capped=%d",capped);}
}
static void configs(struct linebuf *b,int *event) {
    static const char *const names[]={"adas.flag","adas_de.flag","calib.flag","calib_de.flag"};
    static uint32_t old[4];static int seen[4];static off_t sizes[4];static time_t times[4];char buf[65537];int d=directory("/customer/minieye/config");unsigned i;
    for(i=0;i<4;i++){struct stat st;int n=d<0?-1:read_at(d,names[i],buf,sizeof(buf));uint32_t c;
        if(n<0||fstatat(d,names[i],&st,AT_SYMLINK_NOFOLLOW)<0||!S_ISREG(st.st_mode)||st.st_nlink!=1){add(b," cfg.%u=unavailable",i);if(seen[i]==1)*event=1;seen[i]=2;continue;}
        c=crc32_bytes(buf,(size_t)n);if(seen[i]!=1||old[i]!=c||sizes[i]!=st.st_size||times[i]!=st.st_mtime){add(b," cfg_changed=%u",i);*event=1;}
        seen[i]=1;old[i]=c;sizes[i]=st.st_size;times[i]=st.st_mtime;
        add(b," cfg.%u=crc32:%08x,%lld,%lld",i,c,(long long)st.st_size,(long long)st.st_mtime);
        if(i==3)add(b," calib_state=%d",calib_state(buf));
    }if(d>=0)close(d);
}
static void statuses(struct linebuf *b) {
    static const char *const paths[]={"/tmp/c2m_d4_status","/tmp/c2m_debug_status","/tmp/c2m_wifi_status"};static const char *const labels[]={"d4","debug","wifi"};
    static const char *const numeric[]={"rec_status2","rec_status","sd_status"};char buf[4096],path[80];unsigned i;
    for(i=0;i<3;i++){if(read_path(paths[i],buf,sizeof(buf))>=0)safe_status(b,labels[i],buf,(int)i);else add(b," %s.available=0",labels[i]);}
    for(i=0;i<3;i++){unsigned long long v;int n;snprintf(path,sizeof(path),"/tmp/%s",numeric[i]);n=read_path(path,buf,64);if(n>=0){if(n&&buf[n-1]=='\n')buf[--n]=0;if(number(buf,&v)&&v<=UINT32_MAX)add(b," tmp.%s=%llu",numeric[i],v);}}
}
static void kernel_counts(struct linebuf *b,long long mono) {
    static long long last=-60000;static uint32_t previous;static int seen;char buf[16385];int n;unsigned counts[5]={0};const char *const patterns[]={"segfault","Out of memory","Oops:","watchdog","I/O error"};char *p;unsigned i;
    if(mono-last<60000)return;last=mono;
    n=klogctl(3,buf,16384);if(n<0){add(b," kernel_snapshot=unavailable");return;}buf[n]=0;p=buf;
    while(*p){char *e=strchr(p,'\n');if(e)*e=0;for(i=0;i<5;i++)if(strstr(p,patterns[i]))counts[i]++;if(e)*e='\n';else break;p=e+1;}
    {uint32_t c=crc32_bytes(buf,(size_t)n);add(b," kernel_crc32=%08x kernel_changed=%d kernel_counts=%u,%u,%u,%u,%u",c,!seen||c!=previous,counts[0],counts[1],counts[2],counts[3],counts[4]);previous=c;seen=1;}
}
/* Bounded incremental observation of an existing stock log. No raw data is
 * retained in our output; substring counters are advisory, not event totals. */
static void recording_counts(struct linebuf *b) {
    static dev_t device;static ino_t inode;static off_t offset;static int initialized;
    const char *const patterns[]={"Seamless","minieye_msgpack","GPS time","FCW","HMW","LDW","PCW","SAG","VB","adas_fail","tlr_green_on","error","fail"};
    unsigned counts[13]={0},i;char buf[16385];int d=directory("/customer/minieye/log"),fd;struct stat st;ssize_t n;int reset=0;
    if(d<0){add(b," rec_log=unavailable");return;}
    fd=openat(d,"minieye.log",O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);close(d);
    if(fd<0){add(b," rec_log=unavailable");return;}
    if(!plain(fd)||fstat(fd,&st)<0||st.st_size<0){close(fd);add(b," rec_log=unavailable");return;}
    if(!initialized||device!=st.st_dev||inode!=st.st_ino||st.st_size<offset){offset=st.st_size>16384?st.st_size-16384:0;reset=1;}
    device=st.st_dev;inode=st.st_ino;initialized=1;
    n=pread(fd,buf,16384,offset);close(fd);if(n<0){add(b," rec_log=read_error");return;}
    offset+=n;buf[n]=0;
    for(i=0;i<13;i++){const char *p=buf;size_t len=strlen(patterns[i]);while((p=strstr(p,patterns[i]))){counts[i]++;p+=len;}}
    add(b," rec_log_bytes=%ld rec_log_reset=%d rec_log_backlog=%d rec_log_counts=",(long)n,reset,offset<st.st_size);
    for(i=0;i<13;i++)add(b,"%s%u",i?",":"",counts[i]);
}
static long long milliseconds(clockid_t clock) {struct timespec t;if(clock_gettime(clock,&t)<0)return 0;return (long long)t.tv_sec*1000+t.tv_nsec/1000000;}
int main(int argc,char **argv) {
    int once=0,ram,lockfd=-1,rc=0,event;unsigned long long seq=0;long long previous_real=0,previous_mono=0;struct sigaction sa;
    /* No arbitrary production output paths: smoke test uses the SAME safety gates. */
    if(argc!=2||(!strcmp(argv[1],"--once")?(once=1,0):strcmp(argv[1],"--run"))){fprintf(stderr,"usage: c2m-continuous-diag --run | --once\n");return 2;}
    if(geteuid()!=0){fprintf(stderr,"requires root for private lock ownership\n");return 2;}
    umask(077);ram=ram_setup(&lockfd);if(ram<0){fprintf(stderr,"unsafe RAM namespace or already running\n");return 3;}
    memset(&sa,0,sizeof(sa));sa.sa_handler=stop_handler;sigemptyset(&sa.sa_mask);sigaction(SIGTERM,&sa,NULL);sigaction(SIGINT,&sa,NULL);
    do {struct linebuf b={{0},0,0};long long mono=milliseconds(CLOCK_MONOTONIC),real=milliseconds(CLOCK_REALTIME);event=seq==0;seq++;
        add(&b,"v=1 real_ms=%lld mono_ms=%lld logger_pid=%ld sample=%llu hz=%ld page_bytes=%ld",real,mono,(long)getpid(),seq,sysconf(_SC_CLK_TCK),sysconf(_SC_PAGESIZE));
        if(previous_mono&&llabs((real-previous_real)-(mono-previous_mono))>2000){add(&b," rtc_shift_ms=%lld",(real-previous_real)-(mono-previous_mono));event=1;}
        previous_real=real;previous_mono=mono;resources(&b);configs(&b,&event);statuses(&b);kernel_counts(&b,mono);recording_counts(&b);processes(&b,&event);
        /* Leave room to close a truncated sample with a clear marker. */
        if(b.n>sizeof(b.s)-40)b.n=sizeof(b.s)-40;
        if(b.truncated){memcpy(b.s+b.n," truncated=1",12);b.n+=12;}b.s[b.n++]='\n';b.s[b.n]=0;
        rc=append_sample(&b,event,mono);status_write(ram,seq,mono,rc,b.truncated);
        if(!once&&!stopping){long long deadline=mono+5000,remaining;while(!stopping&&(remaining=deadline-milliseconds(CLOCK_MONOTONIC))>0){struct timespec delay={remaining/1000,(remaining%1000)*1000000};(void)nanosleep(&delay,NULL);}}
    }while(!once&&!stopping);
    if(stopping)status_write(ram,seq,milliseconds(CLOCK_MONOTONIC),rc,0);
    close(lockfd);close(ram);return once&&rc?4:0;
}
