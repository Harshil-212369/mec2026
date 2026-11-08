-- Adds the severity level (1-5) that the problem statement requires to the tickets table.
-- Nullable on purpose: the current requester form keeps working. Tickets without a severity
-- are rejected by core/validate.py with "severity: missing" until the form sends one.
-- Safe to run more than once.
-- Run:  psql "$env:MEC_DATABASE_URL" -f scripts/add_severity_column.sql
-- AI-assisted: Claude Code (Anthropic, Claude Opus 5.5), reviewed/modified by Harshil.
ALTER TABLE public.tickets ADD COLUMN IF NOT EXISTS severity integer;
ALTER TABLE public.tickets DROP CONSTRAINT IF EXISTS tickets_severity_check;
ALTER TABLE public.tickets ADD CONSTRAINT tickets_severity_check CHECK (severity BETWEEN 1 AND 5);
