"""ONNX operator audit for SigmaStar-class INT8 IPU (fail-fast gate).

Usage: python3 onnx_operator_audit.py <model.onnx> [--json]
Reports: operators, dynamic shapes, unsupported-risk ops, input/output shapes, model size.
No weights are modified. Requires: pip install onnx (optional; without it, exits 3).

HIGH-RISK defaults for 2022-era SigmaStar IPU (family-level, needs Compiler proof):
  GridSample, DeformConv, LayerNorm/Group/InstanceNorm, NonMaxSuppression/TopK-in-graph,
  Loop/If (control flow), GatherND, Attention/QKV-MatMul hints, Softmax-DFL hint, Resize-bilinear hint.
"""
import sys, json, os

HIGH = {"GridSample", "DeformConv", "LayerNormalization", "GroupNormalization",
        "InstanceNormalization", "NonMaxSuppression", "Loop", "If", "GatherND",
        "Attention", "QAttention", "SkipLayerNormalization", "DeformConv2D",
        "GridSample2D"}
DFL_HINT = {"Softmax", "Reshape", "MatMul"}
RESIZE_HINT = {"Resize"}

def audit(path):
    import onnx
    m = onnx.load(path)
    ops = {}
    for n in m.graph.node:
        ops[n.op_type] = ops.get(n.op_type, 0) + 1
    def shape_of(v):
        try:
            dims = []
            for d in v.type.tensor_type.shape.dim:
                if getattr(d, 'dim_param', ''):
                    dims.append(d.dim_param)
                else:
                    dims.append(getattr(d, 'dim_value', '?'))
            et = v.type.tensor_type.elem_type
            return {"name": v.name, "shape": dims, "elem_type": et}
        except Exception:
            return {"name": getattr(v, 'name', '?'), "shape": "UNKNOWN"}
    inputs = [shape_of(i) for i in m.graph.input]
    outputs = [shape_of(o) for o in m.graph.output]
    dyn = [i for i in inputs if any(isinstance(x, str) for x in i.get("shape", []))]
    bad = sorted(set(ops) & HIGH)
    dfl = sorted(set(ops) & DFL_HINT)
    res = "Resize" in ops
    report = {
        "file": path,
        "bytes": os.path.getsize(path),
        "operators": dict(sorted(ops.items())),
        "inputs": inputs,
        "outputs": outputs,
        "dynamic_inputs": dyn,
        "high_risk_ops": bad,
        "dfl_hint_ops_present": dfl,
        "resize_present": bool(res),
        "verdict": ("HIGH " + str(bad) if bad else ("CHECK-DFL/RESIZE" if (dfl or res) else "LOW (no hard-block seen; still needs vendor-compile proof)")),
    }
    return report

def main():
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        raise SystemExit(2 if len(sys.argv) < 2 else 0)
    as_json = "--json" in sys.argv
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        print(__doc__)
        raise SystemExit(2)
    path = files[0]
    try:
        import onnx  # noqa
    except ImportError:
        print("need: pip install onnx (no model download needed)")
        raise SystemExit(3)
    rep = audit(path)
    if as_json:
        print(json.dumps(rep, indent=2))
    else:
        print("op inventory:")
        for k, v in sorted(rep["operators"].items()):
            flag = "  <-- HIGH-RISK" if k in HIGH else ""
            print(f"  {k}: {v}{flag}")
        print(f"inputs: {rep['inputs']}")
        print(f"outputs: {rep['outputs']}")
        print(f"size: {rep['bytes']} bytes")
        if rep["dynamic_inputs"]:
            print("WARNING: dynamic dims detected (fix to static 1x3xHxW before vendor compile)")
        if rep["resize_present"]:
            print("NOTE: Resize present — force nearest + fixed 2x for old IPU; bilinear is MEDIUM risk")
        if rep["dfl_hint_ops_present"]:
            print("NOTE: Softmax/Reshape/MatMul present — if DFL head, plan plain-regression + CPU decode")
        print("risk:", rep["verdict"])

if __name__ == "__main__":
    main()
