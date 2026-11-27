// 判断事項本文のインライン`code`をコード表示にする（ArtifactデザインのparseDecisions/_segsに合わせる。
// issue #234で返信UI、issue #325で判断待ちカードから使う）。
export default function InlineCode({
  text,
  codeClassName,
}: {
  text: string;
  codeClassName: string;
}) {
  return (
    <>
      {text
        .split(/(`[^`]+`)/)
        .filter(Boolean)
        .map((part, i) =>
          part.length > 1 && part.startsWith("`") && part.endsWith("`") ? (
            <code key={i} className={codeClassName}>
              {part.slice(1, -1)}
            </code>
          ) : (
            <span key={i}>{part.replace(/\*\*/g, "")}</span>
          ),
        )}
    </>
  );
}
