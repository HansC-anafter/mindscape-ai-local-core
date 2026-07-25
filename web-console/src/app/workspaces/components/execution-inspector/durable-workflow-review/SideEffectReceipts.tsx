interface SideEffectReceiptsProps {
  receiptCount: number;
}

export function SideEffectReceipts({
  receiptCount,
}: SideEffectReceiptsProps) {
  return <p className="text-xs">Side-effect receipts: {receiptCount}</p>;
}
