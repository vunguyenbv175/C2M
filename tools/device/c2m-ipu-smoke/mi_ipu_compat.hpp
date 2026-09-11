// mi_ipu_compat.hpp — COMPATIBILITY DECLARATIONS ONLY (UNVERIFIED reconstruction).
// Do NOT treat as vendor headers. Vendor mi_ipu.h / mi_sys.h are required to build
// against real firmware; this file exists only so the skeleton compiles in
// --probe-only documentation mode and so reviewers see EXACTLY what is assumed.
// Every struct below is UNVERIFIED until sizeof/offset checks against the shipped
// libmi_ipu.so (sdk_commit b03a7d4) + on-device MI_IPU_GetInOutTensorDesc pass.
#pragma once
// Safety: this header declares narrow probe-only wrappers; it never defines firmware behavior.
#ifdef C2M_IPU_HAVE_VENDOR_HEADERS
// Preferred path: include real vendor headers supplied privately (never committed).
// #include "mi_ipu.h"
// #include "mi_sys.h"
#endif
// UNVERIFIED assumed signatures (names CONFIRMED in libmi_ipu.so dynsym; arity from
// official MI IPU API doc + local Thumb-2 disasm of IPUCreateDevice/SystemInit):
//   int MI_SYS_Init(int); int MI_SYS_Exit();
//   int MI_IPU_CreateDevice(void* devAttr /*[0]=varSize*/, void*, const char* fwPath, unsigned);
//   int MI_IPU_DestroyDevice();
//   int MI_IPU_CreateCHN(unsigned* chn, void* chnAttr /*inDepth,outDepth*/, void* readFunc, const char* model);
//   int MI_IPU_DestroyCHN(unsigned chn);
//   int MI_IPU_GetInOutTensorDesc(unsigned chn, void* desc);
//   int MI_IPU_GetOutputTensors(unsigned chn, void* vec);
//   int MI_IPU_PutOutputTensors(unsigned chn, void* vec);
//   int MI_IPU_Invoke(unsigned chn, void* inVec, void* outVec);
// Missing on C2M lib (do NOT call): GetInputTensors2/Put2/Invoke2/Custom, CreateCHNWithUserMem, DestroyDeviceExt, CancelInvoke.
