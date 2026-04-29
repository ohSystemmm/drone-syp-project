# Product Guidelines

## Documentation Style: In-depth & Academic
- All documentation should prioritize precision, thoroughness, and a high level of technical detail.
- Complex algorithms and architectural decisions must be clearly explained with references to the underlying principles.
- Avoid overly conversational language; instead, use formal and analytical prose suitable for researchers and advanced developers.

## UX Principles: Safety and Clarity
- **Visual Feedback:** The user interface must provide real-time, high-fidelity status updates for the drone's telemetry, AI detection confidence, and vision-based localization stability.
- **Safety-First Interface:** Emergency controls (e.g., immediate landing, motor cut-off) must be prominently displayed and easily accessible.
- **Informative Error Handling:** System failures or flight anomalies should be reported with specific diagnostic information to aid the user in safe recovery.

## Development Guidelines: Robust and Modular
- **Modular Architecture:** Maintain a strict separation of concerns between core flight control (`GOOSE/core/`) and computer vision modules (`GOOSE/vision/`).
- **Self-Documenting Code:** Code should be highly readable with descriptive variable and function names. Use comprehensive docstrings for all modules, classes, and methods to explain their purpose, parameters, and return values.
- **Robust Testing:** Prioritize automated unit and integration tests for all mission-critical components, especially vision-based positioning and control logic.
- **Reliability and Performance:** Optimization for the drone's hardware constraints and ensuring real-time responsiveness are key considerations during development.
