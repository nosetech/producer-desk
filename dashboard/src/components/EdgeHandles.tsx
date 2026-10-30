import styles from "./EdgeHandles.module.css";

const HANDLES = [
  ["top", styles.top],
  ["bottom", styles.bottom],
  ["left", styles.left],
  ["right", styles.right],
  ["top left", styles.topLeft],
  ["top right", styles.topRight],
  ["bottom left", styles.bottomLeft],
  ["bottom right", styles.bottomRight],
] as const;

/** 親要素（position 指定済み）の上下左右の辺・角に置く、サイズ変更用のつかみ領域。`useEdgeResize` が操作を受ける。 */
export default function EdgeHandles() {
  return (
    <>
      {HANDLES.map(([edges, className]) => (
        <div
          key={edges}
          data-edge={edges}
          aria-hidden="true"
          className={`${styles.handle} ${className}`}
        />
      ))}
    </>
  );
}
