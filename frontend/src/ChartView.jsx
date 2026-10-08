import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Download, Maximize2, X } from "lucide-react";

const CHART_COLORS = [
  "#10a37f",
  "#60a5fa",
  "#f59e0b",
  "#f472b6",
  "#a78bfa",
  "#2dd4bf",
];

function ChartPlot({ chart, height, plotRef }) {
  const data = chart.data.map((point) => ({
    label: point.label,
    ...Object.fromEntries(
      chart.series.map((series, index) => [series, point.values[index]]),
    ),
  }));
  const commonProps = {
    data,
    margin: { top: 8, right: 16, bottom: 8, left: 0 },
  };

  return (
    <div className="w-full" ref={plotRef}>
      <div className="w-full" style={{ height }}>
        <ResponsiveContainer height="100%" minWidth={0} width="100%">
          {chart.type === "pie" ? (
            <PieChart>
              <Pie
                data={data}
                dataKey={chart.series[0]}
                nameKey="label"
                outerRadius={82}
              >
                {data.map((point, index) => (
                  <Cell
                    fill={CHART_COLORS[index % CHART_COLORS.length]}
                    key={point.label}
                  />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          ) : chart.type === "bar" ? (
            <BarChart {...commonProps}>
              <CartesianGrid stroke="#ffffff18" vertical={false} />
              <XAxis dataKey="label" stroke="#ffffff80" tickLine={false} />
              <YAxis
                label={{
                  value: chart.y_axis,
                  angle: -90,
                  position: "insideLeft",
                  fill: "#ffffff80",
                }}
                stroke="#ffffff80"
                tickLine={false}
              />
              <Tooltip />
              {chart.series.length > 1 && <Legend />}
              {chart.series.map((series, index) => (
                <Bar
                  dataKey={series}
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                  key={series}
                  name={series}
                  radius={[4, 4, 0, 0]}
                />
              ))}
            </BarChart>
          ) : (
            <LineChart {...commonProps}>
              <CartesianGrid stroke="#ffffff18" vertical={false} />
              <XAxis dataKey="label" stroke="#ffffff80" tickLine={false} />
              <YAxis
                label={{
                  value: chart.y_axis,
                  angle: -90,
                  position: "insideLeft",
                  fill: "#ffffff80",
                }}
                stroke="#ffffff80"
                tickLine={false}
              />
              <Tooltip />
              {chart.series.length > 1 && <Legend />}
              {chart.series.map((series, index) => (
                <Line
                  dataKey={series}
                  dot={false}
                  key={series}
                  name={series}
                  stroke={CHART_COLORS[index % CHART_COLORS.length]}
                  strokeWidth={2}
                  type="monotone"
                />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-center text-xs text-white/40">
        {chart.x_axis} · {chart.y_axis}
      </p>
    </div>
  );
}

async function downloadChartAsPng(plotElement, title) {
  const source = plotElement?.querySelector("svg");
  if (!source) throw new Error("The chart is not ready to download yet.");

  const { width, height } = source.getBoundingClientRect();
  if (!width || !height) throw new Error("The chart has no visible size.");

  const svg = source.cloneNode(true);
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  svg.setAttribute("width", String(Math.ceil(width)));
  svg.setAttribute("height", String(Math.ceil(height)));
  const background = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "rect",
  );
  background.setAttribute("width", "100%");
  background.setAttribute("height", "100%");
  background.setAttribute("fill", "#171717");
  svg.insertBefore(background, svg.firstChild);

  const svgBlob = new Blob(
    [new XMLSerializer().serializeToString(svg)],
    { type: "image/svg+xml;charset=utf-8" },
  );
  const objectUrl = URL.createObjectURL(svgBlob);
  try {
    const image = new Image();
    image.src = objectUrl;
    await image.decode();
    const scale = 2;
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(width * scale);
    canvas.height = Math.ceil(height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Could not create the chart image.");
    context.fillStyle = "#171717";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);

    const link = document.createElement("a");
    link.download = `${title.trim().replace(/[^a-z0-9-_]+/gi, "-") || "chart"}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function ChartView({ chart }) {
  const [expanded, setExpanded] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const modalPlotRef = useRef(null);

  useEffect(() => {
    if (!expanded) return undefined;
    function closeOnEscape(event) {
      if (event.key === "Escape") setExpanded(false);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [expanded]);

  async function downloadImage(event) {
    event.stopPropagation();
    setDownloadError("");
    try {
      await downloadChartAsPng(modalPlotRef.current, chart.title);
    } catch (error) {
      setDownloadError(error.message);
    }
  }

  return (
    <>
      <section
        aria-label={`${chart.type} chart: ${chart.title}`}
        className="mt-4 w-full cursor-zoom-in rounded-2xl border border-white/10 bg-[#171717] p-4"
        onClick={() => setExpanded(true)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setExpanded(true);
          }
        }}
        role="button"
        tabIndex={0}
        title="Click to enlarge chart"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium">{chart.title}</h3>
          <span className="inline-flex items-center gap-1 text-xs text-white/45">
            <Maximize2 aria-hidden="true" size={14} />
            Enlarge
          </span>
        </div>
        <ChartPlot chart={chart} height={256} />
      </section>

      {expanded && (
        <div
          aria-label={`${chart.type} chart: ${chart.title}`}
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 backdrop-blur-sm md:p-8"
          onClick={() => setExpanded(false)}
          role="dialog"
        >
          <section
            className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#171717] shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="flex items-center justify-between gap-4 border-b border-white/10 px-5 py-4">
              <div className="min-w-0">
                <h2 className="truncate text-lg font-semibold">{chart.title}</h2>
                <p className="mt-1 text-xs text-white/45">
                  {chart.x_axis} · {chart.y_axis}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  aria-label="Download chart as PNG"
                  className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-medium text-black hover:bg-white/85"
                  onClick={downloadImage}
                  type="button"
                >
                  <Download aria-hidden="true" size={16} />
                  <span className="hidden sm:inline">Download PNG</span>
                </button>
                <button
                  aria-label="Close enlarged chart"
                  className="rounded-lg p-2 text-white/65 hover:bg-white/10 hover:text-white"
                  onClick={() => setExpanded(false)}
                  type="button"
                >
                  <X aria-hidden="true" size={19} />
                </button>
              </div>
            </header>
            <div className="min-h-0 flex-1 overflow-auto p-3 md:p-8">
              <ChartPlot chart={chart} height="min(68vh, 680px)" plotRef={modalPlotRef} />
              {downloadError && (
                <p className="mt-3 text-sm text-red-300" role="alert">
                  {downloadError}
                </p>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}

export default ChartView;
