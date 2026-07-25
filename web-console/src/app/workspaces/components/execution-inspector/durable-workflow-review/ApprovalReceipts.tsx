interface ApprovalReceiptsProps {
  openCount: number;
}

export function ApprovalReceipts({ openCount }: ApprovalReceiptsProps) {
  return <p className="text-xs">Open approval receipts: {openCount}</p>;
}
