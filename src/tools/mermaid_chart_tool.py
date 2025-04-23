# app/tools/chart_tools.py
from agno.tools import Toolkit

class MermaidChartTools(Toolkit):
    def __init__(self):
        super().__init__(name="ChartTools")
        self.register(self.make_sales_trend_chart)

    def make_sales_trend_chart(self, data: list[dict]) -> str:
        """
        Devuelve un diagrama Mermaid de la evolución de ventas.
        """
        lines = ["```mermaid", "graph LR"]
        for i in range(len(data)-1):
            a = data[i]["dia"].replace("-", "")
            b = data[i+1]["dia"].replace("-", "")
            lines.append(
                f"{a}[\"{data[i]['dia']}: {data[i]['ventas']}\"] --> "
                f"{b}[\"{data[i+1]['dia']}: {data[i+1]['ventas']}\"]"
            )
        lines.append("```")
        return "\n".join(lines)
