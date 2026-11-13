export function Robot({ small = false }: { small?: boolean }) {
  return (
    <svg
      className={small ? "robot-mark" : "robot-drawing"}
      viewBox="0 0 400 290"
      fill="none"
      role="img"
      aria-label="RoboMaster 轮式机器人线框标识"
    >
      <g
        stroke="currentColor"
        strokeWidth={small ? 6 : 1.7}
        strokeLinejoin="round"
        strokeLinecap="round"
      >
        {!small && (
          <g opacity=".2" strokeWidth="1">
            <path d="M20 240 195 140 380 240M20 210 195 110 380 210M40 260 215 160M75 277 250 177M10 175 190 278M60 150 285 278M110 122 340 256" />
            <ellipse cx="201" cy="222" rx="165" ry="48" strokeDasharray="3 7" />
            <path d="M202 22V275M45 55H359" strokeDasharray="3 7" />
          </g>
        )}
        <path d="m85 147 135-67 113 59-135 70-113-62Z" />
        <path d="M85 147v38l113 63 135-71v-38M198 209v39" />
        <path d="m108 148 113-55 88 46-111 58-90-49Z" />
        <path d="m142 129 55 29 68-34M197 158v39" />
        <path d="m165 101 1-44 55-28 48 26v49M166 57l48 25 55-27M214 82v44" />
        <path d="m175 62 39 21 47-24M186 68v30l29 16 35-18V67" />
        <path d="m215 29 1-14 12-6" />
        <path d="m57 165 24-12 20 11v49l-25 12-19-11v-49Z" />
        <path d="m57 165 19 11 25-12M76 176v49M60 176l14 8M60 188l14 8M60 201l14 8" />
        <path d="m145 214 24-13 20 12v48l-25 13-19-11v-49Z" />
        <path d="m145 214 19 11 25-12M164 225v49M148 225l14 8M148 237l14 8M148 250l14 8" />
        <path d="m272 198 25-13 19 11v45l-25 13-19-11v-45Z" />
        <path d="m272 198 19 10 25-12M291 208v46M295 218l17-9M295 230l17-9M295 242l17-9" />
        <path d="m319 146 25-13 19 11v45l-25 13-19-11v-45Z" />
        <path d="m319 146 19 10 25-12M338 156v46M342 167l17-9M342 179l17-9M342 191l17-9" />
        <path d="m225 218 28-15M225 227l28-15M113 172l26 14" />
        <circle cx="130" cy="148" r="3" />
        <circle cx="221" cy="101" r="3" />
        <circle cx="285" cy="141" r="3" />
        {!small && (
          <g strokeWidth="1" opacity=".55">
            <path d="M33 120V84h90M309 69h52v42M35 245v24h76" />
            <path d="m29 84 4-4 4 4M357 111l4 4 4-4" />
            <path d="M112 253 58 282M332 207l40 21" />
          </g>
        )}
      </g>
      {!small && (
        <g
          fill="currentColor"
          fontFamily="monospace"
          fontSize="8"
          opacity=".55"
        >
          <text x="38" y="78">
            RM / EXPLORATION
          </text>
          <text x="310" y="64">
            Z ↑
          </text>
          <text x="44" y="260">
            01 — CHASSIS
          </text>
          <text x="304" y="273">
            CONCEPT ONLY
          </text>
        </g>
      )}
    </svg>
  );
}
