import { useEffect, useRef, type PointerEvent } from "react";
import drive from "../images/复古CRT故障机械爆炸图.png";
import motor from "../images/赛博朋克爆炸式电机解析图.png";
import control from "../images/复古CRT风格爆炸电路板结构图.png";

export type MechanicalVariant = "drive" | "motor" | "control";
const plates = {
  drive: {
    src: drive,
    name: "轮组与悬挂机械结构爆炸图",
    label: "01 / DRIVE ASSEMBLY",
  },
  motor: {
    src: motor,
    name: "电机转子与定子结构爆炸图",
    label: "02 / MOTOR ANATOMY",
  },
  control: {
    src: control,
    name: "控制板与外壳结构爆炸图",
    label: "03 / CONTROL SYSTEM",
  },
};

/** Original user artwork stays intact; motion is a presentation transform only. */
export function MechanicalArt({
  variant = "drive",
}: {
  variant?: MechanicalVariant;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  const move = (e: PointerEvent<HTMLDivElement>) => {
    if (
      e.pointerType !== "mouse" ||
      matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const box = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width - 0.5) * 10;
    const y = ((e.clientY - box.top) / box.height - 0.5) * 7;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      ref.current?.style.setProperty("--art-x", `${x.toFixed(2)}px`);
      ref.current?.style.setProperty("--art-y", `${y.toFixed(2)}px`);
    });
  };
  const reset = () => {
    cancelAnimationFrame(frame.current);
    ref.current?.style.setProperty("--art-x", "0px");
    ref.current?.style.setProperty("--art-y", "0px");
  };
  const plate = plates[variant];
  return (
    <div
      className={`mechanical-art art-${variant}`}
      ref={ref}
      onPointerMove={move}
      onPointerLeave={reset}
    >
      <img src={plate.src} alt={plate.name} draggable={false} />
      <div className="art-shade" aria-hidden="true" />
      <div className="art-scan" aria-hidden="true" />
      <span className="plate-number">{plate.label}</span>
      <span className="plate-note" title="概念爆炸图，非当前 CAD 模型">
        CONCEPT STUDY
      </span>
    </div>
  );
}

export function MechanicalHero({ prototype = false }: { prototype?: boolean }) {
  return (
    <div className={`mechanical-hero ${prototype ? "prototype-hero" : ""}`}>
      <MechanicalArt variant={prototype ? "motor" : "drive"} />
      <div className="hero-copy">
        <div className="hero-kicker">
          <span className="crosshair">+</span> ROBOMASTER / MECHANICAL
          INTELLIGENCE
        </div>
        <div className="hero-display" aria-hidden="true">
          {prototype ? (
            <>
              MAKE IT
              <br />
              <span>TANGIBLE.</span>
            </>
          ) : (
            <>
              DESIGN
              <br />
              <span>IN MOTION.</span>
            </>
          )}
        </div>
        <h1 className="sr-only">
          {prototype ? "一次性原型机" : "确认组件需求"}
        </h1>
        <div className="hero-bottom">
          <span className="signal-bars" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
            <i />
          </span>{" "}
          HUMAN INTENT. MACHINE PRECISION.
        </div>
      </div>
    </div>
  );
}
