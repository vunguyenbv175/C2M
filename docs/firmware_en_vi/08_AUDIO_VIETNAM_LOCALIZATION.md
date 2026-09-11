# 08 — Audio and Vietnam Localization

## Evidence that VI is a genuine localized/vendor branch

The VI image is not merely a renamed EN TAR.

### ADAS audio differences

Changed files include:

```text
LDW.wav
PCW.wav
SAG.wav
VB.wav
adas_activated.wav
adas_fail.wav
updating.wav
```

`FCW.wav` and `HMW.wav` are unchanged.

### System audio differences in oneed_cust

18/38 oneed files differ, almost entirely audio plus default CGI config.

Changed system prompts include:

```text
Card_Err.wav
Card_Format_Done.wav
Card_Format_Fail.wav
Emergency_FileFull.wav
Format_Card.wav
Insert_Card.wav
Ota_Update_Ok.wav
Rec.wav
Record_Off.wav
Record_On.wav
Replace_Card.wav
Shutter.wav
Stop_Rec.wav
Video_Locked.wav
Video_Unlock.wav
WiFi_Close.wav
WiFi_Open.wav
```

This is strong evidence of language/localization work.

## Audio is not the likely cause of total ADAS failure

The audio list structure is identical.

The core FCW/HMW assets are unchanged.

Therefore audio should be treated as:
- a useful VI donor,
- not the primary regression suspect.

## Reuse recommendation

For C2M Enhanced:

```text
stable EN runtime
+
selected VI Vietnamese audio/resources
```

is a reasonable direction, but every asset should be tested independently and hashed.

## Voice architecture later

Keep safety-critical warnings local.

A future `VoiceManager` can reuse stock Vietnamese prompts where licensing/ownership permits and add user-supplied or newly generated phrase assets separately.
