import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';

export const runtime = 'nodejs';

const repoRoot = path.resolve(process.cwd(), '..');

export async function POST(request: NextRequest) {
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
      + 'asks clarifying questions and compares trims; intent: actively shopping. Specifically looking for options in zip code 94305'
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

    const encoder = new TextEncoder();
    const latestPath = path.resolve(repoRoot, 'web_simulation', 'latest-run.json');

    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        let buffer = '';
        let finalPayload: unknown = null;
        let isClosed = false;

        const closeController = () => {
          if (!isClosed) {
            isClosed = true;
            controller.close();
          }
        };

        const pushLine = (line: string) => {
          if (!line) {
            return;
          }
          try {
            const event = JSON.parse(line);
            if (event?.type === 'complete') {
              finalPayload = event.data;
            }
          } catch (error) {
            console.warn('Failed to parse simulation event', error);
          }
          controller.enqueue(encoder.encode(`${line}\n`));
        };

        child.stdout.setEncoding('utf8');
        child.stdout.on('data', (chunk: string) => {
          buffer += chunk;
          const parts = buffer.split('\n');
          buffer = parts.pop() ?? '';
          for (const part of parts) {
            pushLine(part.trim());
          }
        });

        child.stderr.setEncoding('utf8');
        child.stderr.on('data', (chunk: string) => {
          console.error('Simulation stderr:', chunk);
        });

        child.on('error', (error) => {
          const message = error instanceof Error ? error.message : 'Unknown error';
          controller.enqueue(encoder.encode(`${JSON.stringify({ type: 'error', data: { message } })}\n`));
          closeController();
        });

        child.on('close', async (code) => {
          if (buffer.trim()) {
            pushLine(buffer.trim());
          }

          if (finalPayload) {
            try {
              await fs.writeFile(latestPath, JSON.stringify(finalPayload, null, 2), 'utf8');
            } catch (fileError) {
              console.warn('Failed to persist latest-run.json', fileError);
            }
          }

          if (code !== 0 && finalPayload === null) {
            const message = `Simulation exited with code ${code}`;
            controller.enqueue(encoder.encode(`${JSON.stringify({ type: 'error', data: { message } })}\n`));
          }

          closeController();
        });

        child.stdin.write(resolvedPersona);
        child.stdin.end();
      },
      cancel() {
        child.kill('SIGTERM');
      },
    });

    return new NextResponse(stream, {
      headers: {
        'Content-Type': 'application/x-ndjson',
        'Cache-Control': 'no-cache',
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.error('Simulation error', error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
