import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';

export const runtime = 'nodejs';

const repoRoot = path.resolve(process.cwd(), '..');

async function executeSimulation(persona: string, maxSteps: number) {
  const scriptPath = path.resolve(repoRoot, 'user_sim_car', 'run_web_simulation.py');

  return new Promise<string>((resolve, reject) => {
    const child = spawn('python', [scriptPath, '--max-steps', String(maxSteps)], {
      cwd: repoRoot,
      env: {
        ...process.env,
        PYTHONPATH: repoRoot,
      },
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    child.on('error', (error) => {
      reject(error);
    });

    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `Simulation exited with code ${code}`));
        return;
      }
      resolve(stdout.trim());
    });

    child.stdin.write(persona);
    child.stdin.end();
  });
}

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
      + 'asks clarifying questions and compares trims; intent: actively shopping.'
    );

    const resolvedSteps = Math.min(Math.max(maxSteps ?? 8, 1), 30);
    const output = await executeSimulation(resolvedPersona, resolvedSteps);

    const parsed = JSON.parse(output);

    const latestPath = path.resolve(repoRoot, 'web_simulation', 'latest-run.json');
    try {
      await fs.writeFile(latestPath, JSON.stringify(parsed, null, 2), 'utf8');
    } catch (fileError) {
      console.warn('Failed to persist latest-run.json', fileError);
    }
    return NextResponse.json(parsed);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    console.error('Simulation error', error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
