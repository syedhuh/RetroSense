# RetroSense two-phone comparison

Both logs were processed independently with the same calibration and event-detection pipeline.
Different mounting estimates are expected because the phones may be physically oriented differently.

| Metric | oneplus_gnss_log | nothingphone_gnss_log |
|---|---:|---:|
| Recording duration | 407.7 s | 417.7 s |
| Distance estimated from GPS | 1.78 km | 1.70 km |
| Peak GPS speed | 46.2 km/h | 46.9 km/h |
| Motion-alignment confidence | 0.63 (strong) | 0.37 (moderate) |
| Phone-top heading, left of forward | 3.8° | 95.1° |
| Phone-top tilt, downward | 42.9° | 0.5° |
| Peak forward acceleration | 1.82 m/s² | 1.81 m/s² |
| Peak braking | -6.35 m/s² | -6.52 m/s² |
| Peak lateral acceleration | 1.78 m/s² | 1.65 m/s² |
| Harsh-braking events | 3 | 3 |
| Harsh-acceleration events | 0 | 0 |
| Harsh-cornering events | 0 | 0 |

## Preliminary result

The phones produced comparable peak vehicle-motion values: forward acceleration differed by 0.01 m/s², braking by 0.17 m/s², and lateral acceleration by 0.14 m/s².
The event counts matched across the two logs.

This is evidence that the pipeline can produce similar vehicle-motion summaries from two differently mounted phones on the same drive. It is not yet a ground-truth accuracy measurement; repeat drives will make the conclusion stronger.
