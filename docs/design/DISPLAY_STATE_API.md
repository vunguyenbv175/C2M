# EF-A03 — DisplayState API

`DisplayState` là model trung gian duy nhất giữa mọi provider và mọi màn hình.
Mọi màn hình cụ thể (M4 stock, Web PWA, mock) đều render từ struct này.

```cpp
#include "c2m/display/display_state.hpp"
using namespace c2m::display;
DisplayState s = DisplayState::Now();
s.ego_speed_kmh = 52;
s.speed_limit_kmh = 60;
M4Adapter m4(cfg); m4.Render(s);   // duy nhất M4Adapter biết packet thô
```

Xem header: `include/c2m/display/display_state.hpp`, `i_display_adapter.hpp`,
`m4_adapter.hpp`, `mock_display_adapter.hpp`.
