# tools/research/ai_adas — reusable research tooling (no weights, no device)

```text
model_matrix.py <models.json> <out_prefix>  — normalize metadata → .json/.csv (cols per §50)
onnx_op_inventory.py <model.onnx>           — fail-fast op gate (needs `pip install onnx`)
license_check.py <models.json>              — heuristic NC/copyleft flag (NOT legal advice)
```

`models.json` shape: list of `{model,task,source,license,params,input,flops,metric,export_onnx,int8,op_risk,ipu_feas,cpu_feas,android_feas,value}`; missing → `UNKNOWN`.
Do not commit weights, clips, or PII datasets. See `docs/research/C2M_AI_*_V1.md`.
