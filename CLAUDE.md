# Cost Control Rules

- Never load files larger than 100 lines into context unless explicitly needed.
- For simple tasks like reading files or checking status, suggest switching to a cheaper model with /model before starting.
- On long sessions, remind the user to run /compact every 30 minutes.
- Reserve Opus for complex architecture, hard debugging, and quality-critical tasks.
