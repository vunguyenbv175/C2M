#!/usr/bin/env python3
import msgpack
from libflow_protocol import pack_subscription,decode_ws_binary

def main():
    sub=msgpack.unpackb(pack_subscription('test','vehicle'),raw=False)
    assert sub=={'source':'test','topic':'subscribe','data':'vehicle'}

    inner={
        'frame_id':1,'time':2,'key':'vehicleWarning',
        'data':{
            'vehicle_id':3,'headway':1.2,'warning_level':0,
            'fcw':0,'headway_warning':0,'vb_warning':0,'sag_warning':0,
        },
    }
    outer={
        'time':4,'source':'AdasScreenService','topic':'vehicle',
        'data':msgpack.packb(inner,use_bin_type=True),
    }
    r=decode_ws_binary(msgpack.packb(outer,use_bin_type=True))
    assert r.inner==inner
    assert not r.warnings,r.warnings
    print('synthetic protocol smoke: OK')

if __name__=='__main__':main()
