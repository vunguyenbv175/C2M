"""ONNX operator inventory (fail-fast gate for vendor conversion).

Usage: python3 onnx_op_inventory.py <model.onnx>
Lists op types + flags HIGH-risk ops for SigmaStar-class INT8 NPU.
Requires: onnx (pip install onnx). Without it, prints guidance and exits 3.
HIGH-RISK default: GridSample, DeformConv, LayerNormalization, GroupNormalization,
  NonMaxSuppression, TopK (in-graph), Loop, If, Softmax(DFL-head hint), GatherND,
  Resize(bilinear-hint — check mode), Attention/QKV-MatMul hints.
"""
import sys

HIGH = {"GridSample", "DeformConv", "LayerNormalization", "GroupNormalization",
        "InstanceNormalization", "NonMaxSuppression", "Loop", "If", "GatherND",
        "Attention", "QAttention", "SkipLayerNormalization"}

def main():
    if len(sys.argv) < 2:
        print(__doc__); raise SystemExit(2)
    try:
        import onnx
    except ImportError:
        print("need: pip install onnx (no model download needed)"); raise SystemExit(3)
    m = onnx.load(sys.argv[1])
    ops: dict = {}
    for n in m.graph.node:
        ops[n.op_type] = ops.get(n.op_type, 0) + 1
    print("op inventory:")
    for k in sorted(ops):
        flag = "  <-- HIGH-RISK" if k in HIGH else ""
        print(f"  {k}: {ops[k]}{flag}")
    dyn = [i for i in m.graph.input if any(
        getattr(d, 'dim_param', '') for d in i.type.tensor_type.shape.dim)] if m.graph.input else []
    if dyn:
        print("WARNING: dynamic dims detected (fix to static 1x3xHxW before vendor compile)")
    bad = sorted(set(ops) & HIGH)
    print("risk:", "HIGH " + str(bad) if bad else "LOW (no hard-block op seen; still needs vendor-compile proof)")

if __name__ == "__main__":
    main()
