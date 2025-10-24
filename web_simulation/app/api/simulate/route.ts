import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';

export const runtime = 'nodejs';

const repoRoot = path.resolve(process.cwd(), '..');

export async function POST(request: NextRequest) {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  try {
    const body = await request.json();
    const persona = typeof body.persona === 'string' && body.persona.trim().length > 0
      ? body.persona.trim()
      : undefined;
    const maxStepsRaw = body.maxSteps;
    const maxStepsNumber = Number(maxStepsRaw);
    const maxSteps = Number.isFinite(maxStepsNumber) ? maxStepsNumber : undefined;

    const resolvedPersona = persona ?? (
      'Married couple in Colorado with a toddler and a medium-sized dog. Mixed city/highway commute; '
      + 'budget-conscious but safety-focused. Considering SUVs and hybrids; casually written messages with occasional typos; '
      + 'asks clarifying questions and compares trims; intent: actively shopping.'
    );

    const resolvedSteps = Math.min(Math.max(maxSteps ?? 8, 1), 30);
    const scriptPath = path.resolve(repoRoot, 'user_sim_car', 'run_web_simulation.py');

    const child = spawn('python', [scriptPath, '--max-steps', String(resolvedSteps)], {
      cwd: repoRoot,
      env: {
        ...process.env,
        PYTHONPATH: repoRoot,
      },
    });

    child.stdin.write(resolvedPersona);
    child.stdin.end();

    let stderr = '';
    let stdoutBuffer = '';
    let latestPayload: unknown = null;

    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const forwardLine = (rawLine: string, ensureNewline = true) => {
          const trimmed = rawLine.trim();
          if (trimmed) {
            try {
              const event = JSON.parse(trimmed);
              if (event && event.type === 'complete') {
                latestPayload = event.payload;
              }
            } catch (parseError) {
              console.warn('Failed to parse simulation line', parseError, trimmed);
            }
          }
          const payload = ensureNewline ? `${rawLine}\n` : rawLine;
          controller.enqueue(encoder.encode(payload));
        };

        const drainBuffer = (final = false) => {
          let newlineIndex = stdoutBuffer.indexOf('\n');
          while (newlineIndex >= 0) {
            const line = stdoutBuffer.slice(0, newlineIndex);
            stdoutBuffer = stdoutBuffer.slice(newlineIndex + 1);
            forwardLine(line);
            newlineIndex = stdoutBuffer.indexOf('\n');
          }
          if (final && stdoutBuffer.length) {
            const remaining = stdoutBuffer;
            stdoutBuffer = '';
            forwardLine(remaining, false);
          }
        };

        child.stdout.on('data', (chunk: Buffer) => {
          const text = decoder.decode(chunk, { stream: true });
          stdoutBuffer += text;
          drainBuffer();
        });

        child.stderr.on('data', (chunk: Buffer) => {
          const text = decoder.decode(chunk, { stream: true });
          stderr += text;
          console.error('Simulation stderr:', text.trim());
        });

        child.on('error', (error) => {
          const message = JSON.stringify({ type: 'error', message: error.message });
          controller.enqueue(encoder.encode(`${message}\n`));
          controller.close();
        });

        child.on('close', async (code) => {
          const remaining = decoder.decode();
          if (remaining) {
            stdoutBuffer += remaining;
          }
          drainBuffer(true);

          if (code !== 0) {
            const errorEvent = {
              type: 'error',
              message: stderr.trim() || `Simulation exited with code ${code}`,
            };
            controller.enqueue(encoder.encode(`${JSON.stringify(errorEvent)}\n`));
          } else if (latestPayload) {
            const latestPath = path.resolve(repoRoot, 'web_simulation', 'latest-run.json');
            try {
              await fs.writeFile(latestPath, JSON.stringify(latestPayload, null, 2), 'utf8');
            } catch (fileError) {
              console.warn('Failed to persist latest-run.json', fileError);
            }
          }

          controller.close();
        });
      },
      cancel() {
        child.kill();
      },
    });

    return new NextResponse(stream, {
      headers: {
        'Content-Type': 'application/x-ndjson',
        'Cache-Control': 'no-store',
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.error('Simulation error', error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
