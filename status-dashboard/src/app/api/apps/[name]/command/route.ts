import { NextRequest, NextResponse } from "next/server";
import { OVERMIND_PROCESSES } from "@/lib/constants";
import { restartProcess } from "@/lib/overmind";

const VALID_NAMES: string[] = OVERMIND_PROCESSES.map((p) => p.name);

interface CommandRequest {
  command: "restart";
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params;

  if (!VALID_NAMES.includes(name)) {
    return NextResponse.json(
      { success: false, error: `Unknown process: ${name}. Valid: ${VALID_NAMES.join(", ")}` },
      { status: 404 }
    );
  }

  let body: CommandRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  if (body.command !== "restart") {
    return NextResponse.json(
      { success: false, error: `Unsupported command: ${body.command}. Only "restart" is supported.` },
      { status: 400 }
    );
  }

  const success = await restartProcess(name);

  return NextResponse.json({ success });
}
