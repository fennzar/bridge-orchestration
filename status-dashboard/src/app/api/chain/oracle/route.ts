import { NextResponse } from "next/server";
import { oracleGet, oracleSet } from "@/lib/rpc";

export const dynamic = "force-dynamic";

export async function GET() {
  const price = await oracleGet();
  return NextResponse.json({ price });
}

export async function POST(request: Request) {
  let body: { price?: number };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  if (typeof body.price !== "number" || body.price <= 0) {
    return NextResponse.json(
      { success: false, error: "price must be a positive number" },
      { status: 400 }
    );
  }

  const success = await oracleSet(body.price);
  return NextResponse.json({ success });
}
