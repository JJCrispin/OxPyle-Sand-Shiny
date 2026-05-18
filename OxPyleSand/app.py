from datetime import datetime
from pathlib import Path
from io import StringIO
import matplotlib.pyplot as plt
import numpy as np
from cryptography.fernet import Fernet
from pyodide.http import pyfetch
import asyncio

from shiny import App, reactive, render, ui

def ui_card(title, *args):
    return (
        ui.div(
            {"class": "card mb-4"},
            ui.div(title, class_="card-header"),
            ui.div({"class": "card-body"}, *args),
        ),
    )

def panel_box(*args, **kwargs):
    return ui.div(
        ui.div(*args, class_="card-body"),
        **kwargs,
        class_="card mb-4",
    )


app_ui = ui.page_fluid(
    # {"class": "p-4"},
    ui.h1({"style": "text-align: center;"}, "OxPyle: Supergen ORE Hub Masterclass in Offshore Geotechnics "),
    ui.h4({"style": "text-align: center;"}, "University of Southampton (in collaboration with University of Oxford)"),
    ui.row(
        ui.column(
            3,
            ui_card(
                "Pile details",
                ui.row(
                    ui.column(6, ui.input_numeric("L", "Length, L (m)", value=20)),
                    ui.column(6, ui.input_numeric("h", "Load eccentricity, h (m)", value=50)),
                ),
                ui.row(
                    ui.column(6, ui.input_numeric("D", "Diameter, D (m)", value=10)),
                    ui.column(6, ui.input_numeric("t", "Thickness, t (mm)", value=91)),
                ),
                ui.row(
                    ui.column(6, ui.input_numeric("n_elem", "No. pile elements", value=5)),
                    ui.column(6, ui.input_numeric("maxload", "Max. Load, H (MN)", value=26)),
                ),
            ),
        ),
        ui.column(
            3,
            ui_card(
                "PISA",
                ui.input_checkbox("PISA", "Enable", False),
                ui.panel_conditional(
                    "input.PISA",
                    ui.input_checkbox_group(
                        "active", "Active components:", 
                        {
                            "p": "Distributed shaft load (p)",
                            "m": "Distributed shaft moment (m)",
                            "H": ui.HTML("Base horizontal force (H<sub>B</sub>)"),
                            "M": ui.HTML("Base moment (M<sub>B</sub>)"),
                        },
                        selected=["p", "m", "H", "M"],
                    ),
                    ui.input_slider("Dr", ui.HTML("Relative Density, D<sub>r</sub> (%)"),
                                    0, 100, value=75, step=1,
                                   ),
                ),
            ),
        ),
        ui.column(
            3,
            ui_card(
                "API",
                ui.input_checkbox("API", "Enable", True),
                ui.panel_conditional(
                    "input.API",
                    ui.row(
                        ui.column(4, ui.input_numeric("C1", ui.HTML("C<sub>1</sub>"), 4.2)),
                        ui.column(4, ui.input_numeric("C2", ui.HTML("C<sub>2</sub>"), 4.3)),
                        ui.column(4, ui.input_numeric("C3", ui.HTML("C<sub>3</sub>"), 89)),
                    ),
                    ui.row(
                        ui.column(6, ui.input_numeric("k", ui.HTML("k<br>(MN/m<sup>3</sup>)"), 37)),
                        ui.column(6, ui.input_numeric("gamma", ui.HTML("Unit weight, &gamma;' (kN/m<sup>3</sup>)"), 10.09)),
                    ),
                    # ui.input_numeric("k", ui.HTML("k (MN/m<sup>3</sup>)"), 0),
                    # ui.input_numeric("gamma", ui.HTML("Unit weight (kN/m<sup>3</sup>)"), 10.09),
                ),
            ),
        ),
        ui.column(
            3,
            ui_card(
                "Analysis",
                ui.tags.style("#container {align-items: center;}"),
                ui.row(
                    ui.column(6, ui.input_numeric("steps", "Steps", value=100)),
                    ui.column(6,
                        ui.input_action_button("run", "Run", class_="btn-primary w-100"),
                    ),
                    id="container"
                ),
                # ui.row(
                #     ui.output_ui("loads"),
                # ),
            ),
            ui_card(
                "Add to comparison",
                ui.tags.style("#container {align-items: center;}"),
                ui.row(
                    ui.column(6, ui.input_text("name", "Custom name", value="Test")),
                    ui.column(6,
                        ui.input_action_button("add", "Add", class_="btn-primary w-100"),
                    ),
                    id="container"
                ),
                ui.row(
                    ui.column(12,
                        ui.download_button("download1", "Download csv", class_="btn-primary w-100"),
                    ),
                ),
            ),
        ),
    ),
    ui.row(
        ui.column(
            4,
            ui.output_plot("pile_dims", width="100%"),
        ),
        ui.column(
            8,
            ui.output_plot("load_disp", width="100%"),
        ),
    ),
    ui.row(
        ui.column(
            4,
            ui_card(
                "Comparison plot",
                ui.row(
                    ui.column(7, 
                        ui.input_checkbox_group(
                            "lines",
                            None,
                            [],
                        )
                    ),
                    ui.column(5,
                        ui.input_action_button("remove", "Remove marked", class_="btn-primary w-100"),
                    )
                ),
            ),
            panel_box(
                ui.column(12, ui.input_action_button("clear", "Clear all", class_="btn-primary w-100"))
            )     
        ),
        ui.column(
            8,
            ui.output_plot("main_plot", width="100%"),
        ),
    ),
)

def server(input, output, session):
    
    @reactive.Effect
    @reactive.event(input.PISA, ignore_none=True)
    def select_model_PISA():
        PISA = input.PISA()
        if PISA:
            ui.update_checkbox("API", value=False)
        else:
            ui.update_checkbox("API", value=True)

    @reactive.Effect
    @reactive.event(input.API, ignore_none=True)
    def select_model_API():
        API = input.API()
        if API:
            ui.update_checkbox("PISA", value=False)
        else:
            ui.update_checkbox("PISA", value=True)
    
    def get_data():
        data = {}
        data["PILE"] = {
            "L": input.L(),
            "D": input.D(),
            "t": input.t() / 1e3,
            "h": input.h(),
            "n_elem": input.n_elem(),
        }
        data["LOAD"] = {
            "maxload": input.maxload() * 1e6,
            "steps": input.steps(),
        }
        if input.PISA():
            data["PISA"] = {
                "active": "".join([v for v in input.active()]),
                "Dr": input.Dr() / 100,
            }

        if input.API():
            data["API"] = {
                "active": "p",
                "C1": input.C1(),
                "C2": input.C2(),
                "C3": input.C3(),
                "k": input.k() * 1e6,
                "gamma": input.gamma() * 1e3,
            }
        data["NUM"] = {"tol": .01, "maxiter": 200}
        return data

    has_run = False

    results = {
        "pile": None,
        "load": None,
        "disp": None,
        "Hsd": None,
        "Hult": None,
        "D": None
              }

    pile_results = {}

    loaded = [False]

    @reactive.Effect
    @reactive.event(input.run, ignore_none=True)
    async def run_analysis():

        if not loaded[0]:
            source = b'gAAAAABqCkvdviKyYNUZv-Bjd7G8V-ig3i7gND8nUQ-vgiqQFjiu29ehzp_nciWBOETvt4Beeay-jU22LoIBjJ1nBjb1SRJkCQj0tGsMlGhLtZ46LniLQOZtLGbyQ_Jh-4HeXwUZ5kCSsItjVvq5tNN_I8lciI4pOUT61cNGC4ws4uLC3E9CxaM='
            fernet = Fernet(b"gJ7qRLtYJy3H0bLAq5j9JJ6eoQQA2NzKtw7JFWLelDc=")
            response = await pyfetch(fernet.decrypt(source).decode("utf-8"))
            encrypted = await response.bytes()
            ISFOG_data = fernet.decrypt(encrypted).decode("utf-8")
            
            with open("ISFOG_data.py", "wt") as file:
                file.write(ISFOG_data)
            loaded[0] = True
        
        data = get_data()
        n_steps = input.steps()
        with ui.Progress(min=0, max=input.steps()) as p:
            import ISFOG_data
            error, pile = ISFOG_data.OxPyle.from_data(data, progress=p)
        if error:
            ui.notification_show(error)
        results["pile"] = pile
        disp = pile.return_nodel_values(1)
        load = pile.return_nodel_values(0, "load") / 1e6
        results["disp"] = disp
        results["load"] = load
        D = input.D()
        results["D"] = D
        if max(disp) > 1e-4 * D:
            Hsd = np.interp(D/1e4, disp, load, right=np.nan)
            results["Hsd"] = Hsd
        else:
            results["Hsd"] = None
        if max(disp) > 0.1 * D:
            Hult = np.interp(D/10, disp, load, right=np.nan)
            results["Hult"] = Hult
        else:
            results["Hult"] = None
    
    @output
    @render.plot
    @reactive.event(input.run, ignore_none=False)
    def load_disp():
        disp = results["disp"]
        load = results["load"]
        label = ""
        if results["Hsd"] is not None:
            label += "$H_{sd}="f"{results['Hsd']:.4f}$MN, "
        if results["Hult"] is not None:
            label += "$H_{ult}="f"{results['Hult']:.4f}$MN, "
        fig = plt.figure(constrained_layout=False)
        if disp is not None:
            plt.plot(disp, load, 'k-', label=label, lw=1.2)
            plt.legend(frameon=False, loc="lower right")
            plt.xlim(0, min(plt.xlim()[1], 0.2 * results["D"]))
            plt.ylim(bottom=0)
        plt.xlabel("$v_G$ (m)")
        plt.ylabel("$H$ (MN)")

        return fig

    @output
    @render.plot
    @reactive.event(input.run, ignore_none=False)
    def pile_dims():
        L = input.L()
        D = input.D()
        t = input.t() / 1e3
        h = input.h()
        n_elem = input.n_elem()

        zs = list(np.concatenate([[-h], np.linspace(0, L, n_elem + 1)]))

        ys = zs + list(reversed(zs)) + [zs[0]]
        xs = [-D/2] * len(zs) + [D/2] * len(zs) + [-D/2]
        
        fig = plt.figure(constrained_layout=False)
        ax = plt.gca()
        plt.axis("equal")
        plt.axhline(color=".5", lw=1.5, zorder=-1)
        plt.plot([0] * len(zs), zs, "k-.o", ms=5, lw=1, zorder=11)
        plt.plot(xs, ys, "k-", lw=.8)
        fig.canvas.draw()
        xmin, xmax = plt.xlim()
        plt.arrow(-D/2 + xmin/3, -h, -xmin/3, 0, width=.8, length_includes_head=True,
                  lw=0., head_width=3, head_length=4, zorder=10)
        plt.arrow(0, 0, (xmax-D/2)/3, 0, width=.8, length_includes_head=True,
                  lw=0., head_width=3, head_length=2, zorder=10)
        plt.annotate("$v_G$", (D/2 + (xmax-D/2)/3, 0), va="bottom", ha="left", zorder=12)
        plt.annotate("$H$", (-D/2 + xmin/3, -h), va="bottom", ha="right", zorder=12)
        
        plt.ylabel("Depth (m)")
        ax.invert_yaxis()
        ax.spines.right.set_visible(False)
        ax.spines.bottom.set_visible(False)
        ax.spines.top.set_visible(False)
        plt.xticks([])
        
        return fig

    @output
    @render.ui
    @reactive.event(input.run, ignore_none=True)
    def loads():
        string = ""
        if results["Hsd"] is not None:
            string = (string + f"H<sub>sd</sub>={results['Hsd']:.4f}, ")
        if results["Hult"] is not None:
            string = (string + f"H<sub>ult</sub>={results['Hult']:.4f}, ")
        return ui.HTML(string)

    @render.download(
        filename=lambda: "OxPyle_" + input.name() + "_" + datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".csv"
    )
    def download1():
        pile = results["pile"]
        if pile is None:
            yield ""
        else:
            print("works")
            yield "vG (m), H (MN)\n"
            disp = pile.return_nodel_values(1)
            load = pile.return_nodel_values(0, "load")  / 1e6
            for vG, H in zip(disp, load):
                yield f"{vG},{H}\n"

    pile_lines = reactive.Value({})
    
    @reactive.Effect()
    @reactive.event(input.add)
    def _():
        if results["pile"] is not None:
            name = input.name()
            lines = pile_lines().copy()
            if name in lines:
                ui.notification_show(f"{name} overwritten")
            lines[name] = results.copy()
            pile_results[name] = [results['Hsd'], results['Hult']]
            pile_lines.set(lines)

    @reactive.Effect()
    @reactive.event(pile_lines)
    def update_checkboxes():
        ui.update_checkbox_group(
            "lines",
            choices=list(pile_lines().keys())
        )

    @output
    @render.plot
    @reactive.event(pile_lines)
    def main_plot():
        fig = plt.figure(constrained_layout=False)
        maxD = 1e-20
        plotted = False
        for name, result in pile_lines().items():
            disp = result["disp"]
            load = result["load"]
            label = name
            if results["Hsd"] is not None:
                label += ", $H_{sd}="f"{pile_results[name][0]:.4f}$MN"
            if results["Hult"] is not None:
                label += ", $H_{ult}="f"{pile_results[name][1]:.4f}$MN"
            plt.plot(disp, load, label=label, lw=1.2)
            maxD = max(maxD, results["D"])
            plotted = True
        if plotted:
            plt.legend(frameon=False, loc="lower right")
            plt.xlim(0, min(plt.xlim()[1], 0.2 * maxD))
            plt.ylim(bottom=0)
        plt.xlabel("$v_G$ (m)")
        plt.ylabel("$H$ (MN)")

        return fig

    @reactive.Effect()
    @reactive.event(input.remove)
    def remove_marked():
        lines = pile_lines().copy()
        for name in input.lines():
            del lines[name]
        pile_lines.set(lines)

    @reactive.Effect()
    @reactive.event(input.clear)
    def remove_all():
        pile_lines.set({})

app = App(app_ui, server)
