#!/usr/bin/env python3
"""Synthetic smoke test for discover_transport.py."""
from pathlib import Path
from tempfile import TemporaryDirectory
from discover_transport import summarize


def write(root: Path, rel: str, text: str):
    p=root/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')


def make_base(root: Path):
    write(root,'processes.tsv','10\tcardv\t/bootconfig/bin/cardv\n20\tadas\t/customer/minieye/adas/adas\n')
    write(root,'proc_net_arp.txt','IP address       HW type     Flags       HW address            Mask     Device\n')
    write(root,'proc_net_tcp.txt','  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n')
    write(root,'proc_input_devices.txt','')
    write(root,'sys_class_net/wlan0/address','00:11:22:33:44:55\n')
    write(root,'sys_class_net/wlan0/operstate','up\n')
    write(root,'sys_class_net/wlan0/carrier','1\n')


def make_m4_on(root: Path):
    make_base(root)
    write(root,'sys_class_net/usb0/address','02:00:00:00:00:01\n')
    write(root,'sys_class_net/usb0/operstate','up\n')
    write(root,'sys_class_net/usb0/carrier','1\n')
    write(root,'usb/1-1/idVendor','1234\n')
    write(root,'usb/1-1/idProduct','5678\n')
    write(root,'usb/1-1/product','Synthetic M4\n')
    write(root,'proc_net_arp.txt','IP address       HW type     Flags       HW address            Mask     Device\n192.168.32.1     0x1         0x2         02:00:00:00:00:02     *        usb0\n')
    write(root,'proc_net_tcp.txt','  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n   0: 00000000:659C 0120A8C0:1234 01 00000000:00000000 00:00000000 00000000 0 0 111\n')
    write(root,'proc_20_adas/fd.txt','3 -> socket:[111]\n')


def main():
    with TemporaryDirectory() as td:
        base=Path(td); off=base/'off'; on=base/'on'; off.mkdir(); on.mkdir()
        make_base(off); make_m4_on(on)
        r=summarize(off,on)
        assert 'usb0' in r['new_interfaces'], r
        assert '1-1' in r['new_usb_devices'], r
        assert any(x['ip']=='192.168.32.1' for x in r['new_arp_peers']), r
        assert any(x['local_port']==26012 for x in r['new_sockets']), r
        assert any(e['kind']=='new_network_interface' and e['score']==100 for e in r['ranked_evidence']), r
        assert any(e['kind']=='new_socket' and e['score']==100 for e in r['ranked_evidence']), r
        print('OK synthetic M4 transport discovery')

if __name__=='__main__': main()
