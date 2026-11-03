-- Kohu migration 0006 (up): agent run trace.
-- Runs record who asked (persona and user from the signed token). Step
-- kinds become the agent loop's: model, tool, answer, fallback, result.
-- The template planner's subtask table is no longer written.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS persona TEXT;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE run_steps DROP CONSTRAINT IF EXISTS run_steps_agent_check;
ALTER TABLE run_steps ADD CONSTRAINT run_steps_agent_check CHECK (agent IN (
  'planner', 'retrieval', 'policy', 'verifier', 'conflict',
  'model', 'tool', 'answer', 'fallback', 'result'));
