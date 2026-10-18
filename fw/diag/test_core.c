#include "diag_core.h"
#include <assert.h>
static void stat_tests(void) {
    char s[2048]; struct procinfo p;
    strcpy(s,"123 (odd ) name) S 7 0 0 0 0 0 0 0 0 0 101 202 -1 -1 3 0 2 0 100000 90 5\n");
    assert(parse_stat(s,&p)); assert(p.ppid==7&&p.utime==101&&p.stime==202&&p.start==100000&&p.rss==5&&p.state=='S');
    strcpy(s,"123 (adas) S 1"); assert(!parse_stat(s,&p));
    strcpy(s,"123 adas S 1"); assert(!parse_stat(s,&p));
}
int main(void) {
    struct linebuf b={{0},0,0}; unsigned long long v; char s[2048]; unsigned i;
    assert(crc32_bytes("123456789",9)==0xcbf43926u);
    assert(number("18446744073709551615",&v));assert(!number("18446744073709551616",&v));
    assert(!number("-1",&v)&&!number("1 ",&v)&&!number("",&v));
    assert(calib_state("--install_calib_state=1\n")==1);
    assert(calib_state("x=3\n--install_calib_state=2\n")==2);
    assert(calib_state("--install_calib_state=2")==2);
    assert(!calib_state("prefix--install_calib_state=2\n"));
    assert(!calib_state("--install_calib_state=20\n"));
    assert(!calib_state("--install_calib_state=2\r\n"));
    assert(!calib_state("--install_calib_state=1\n--install_calib_state=2\n"));
    assert(!calib_state("--install_calib_state=0\n"));
    assert(!strcmp(proc_name("lane_accelerato"),"lane_accelerator"));
    assert(!strcmp(proc_name("lane_postproces"),"lane_postprocess"));
    assert(!proc_name("lane_accelerat"));assert(!proc_name("adas-malicious"));
    assert(mount_line("/dev/mmcblk0p1 /mnt/mmc vfat rw,relatime 0 0"));
    assert(mount_line("/dev/mmcblk0 /mnt/mmc vfat rw 0 0"));
    assert(!mount_line("/dev/mmcblk0p2 /mnt/mmc vfat rw 0 0"));
    assert(!mount_line("/dev/mmcblk0p1 /mnt/mmc vfat ro,relatime 0 0"));
    assert(!mount_line("/dev/mmcblk0p1 /mnt/mmc2 vfat rw 0 0"));
    assert(!needs_rotation(DIAG_SLOT_BYTES-100,100));
    assert(needs_rotation(DIAG_SLOT_BYTES-100,101));
    assert(needs_rotation(DIAG_SLOT_BYTES+1,0));
    assert(needs_rotation(0,DIAG_SLOT_BYTES+1));
    strcpy(s,"state=ready\ngps_fresh=1\nactive=1\nsequence=123\nspeed=99\ndistance_m=20\nevent_id=SECRET\nlatitude=SECRET\nstate=SECRET\n");safe_status(&b,"d4",s,0);
    assert(strstr(b.s,"d4.state=ready")&&strstr(b.s,"d4.sequence=123"));
    assert(!strstr(b.s,"SECRET")&&!strstr(b.s,"speed")&&!strstr(b.s,"distance")&&!strstr(b.s,"latitude"));
    strcpy(s,"state=active\nwindow_sec=0\nlifetime=boot\nkey_fp=SECRET\nbind=SECRET\n");safe_status(&b,"debug",s,1);
    assert(strstr(b.s,"debug.lifetime=boot")&&!strstr(b.s,"SECRET"));
    strcpy(s,"sta_state=connected\nsta_ssid=SECRET\nsta_ipv4=SECRET\nlast_error=SECRET\nsta_supported=yes\n");safe_status(&b,"wifi",s,2);
    assert(strstr(b.s,"wifi.sta_state=connected")&&!strstr(b.s,"SECRET"));
    for(i=0;i<20000;i++)add(&b,"0123456789");assert(b.truncated&&b.n<DIAG_CAP);
    stat_tests();puts("PASS: CRC, strict numeric/calibration, truncated comm, stat, mount gates, rotation bounds, privacy, output bound");return 0;
}
