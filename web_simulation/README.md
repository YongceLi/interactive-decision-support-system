# Simulation Demo UI

A standalone Next.js application that replays the autonomous user simulator for
the car recommendation assistant. The UI does **not** accept chat input; it
simply configures a persona seed and step limit, invokes the simulator, and
renders each turn (assistant reply, user response, UI actions, RL scores, and
judge verdict).

## Getting Started

```bash
cd web_simulation
npm install
npm run dev
```

The API route spawns the Python simulator in `../user_sim_car`. Ensure your
Python environment is configured exactly as described in
[`user_sim_car/README.md`](../user_sim_car/README.md) (LLM credentials, backend
URL, dependencies).

- `POST /api/simulate` accepts `{ persona: string, maxSteps: number }`.
- The persona defaults to the Colorado family shopper described in the project
  brief if omitted.
- `maxSteps` is clamped between 1 and 30 and defaults to 8.

To customize the LLM model or temperature, update
`user_sim_car/run_web_simulation.py` or wrap it in your own script and adjust
the API handler accordingly.
