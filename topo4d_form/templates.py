from fasthtml.common import *
import json
import os

from .styles import *
from .validation import model_required_keys
from .make_item import (
    construct_topo4d_properties,
    construct_assets,
    create_pystac_item,
)


######################
### HTML Templates ###
######################
def inputTemplate(
    label,
    name,
    val,
    placeholder=None,
    error_msg=None,
    input_type="text",
    canValidateInline=False,
):
    return Div(
        hx_target="this",
        hx_swap="outerHTML",
        cls=f"{error_msg if error_msg else 'Valid'}",
        style=control_container_style,
    )(
        labelDecoratorTemplate(Label(label), name in model_required_keys),
        Input(
            id=name,
            name=name,
            type=input_type,
            placeholder=placeholder,
            value=f"{val}",
            hx_post=f"/{name.lower()}" if canValidateInline else None,
            style=text_input_style,
        ),
        Div(f"{error_msg}", style="color: red;") if error_msg else None,
    )

def inputListTemplate(
    label,
    name,
    placeholder=None,
    values=[None, None, None, None],
    error_msg=None,
    input_type="number",
    canValidateInline=False,
):
    return Div(
        hx_target="this",
        hx_swap="outerHTML",
        cls=f"{error_msg if error_msg else 'Valid'}",
        style=control_container_style,
    )(
        labelDecoratorTemplate(Label(label), name in model_required_keys),
        Div(
            style="display: flex; gap: 20px; justify-content: flex-start; width: 100%; max-width: 600px;"
        )(
            *[
                Input(
                    name=f"{name.lower()}_{i + 1}",
                    id=f"{name.lower()}_{i + 1}",
                    placeholder=placeholder,
                    type=input_type,
                    value=val,
                    style="width: 160px;",
                    hx_post=f"/{name.lower()}" if canValidateInline else None,
                )
                for i, val in enumerate(values)
            ]
        ),
        Div(f"{error_msg}", style="color: red;") if error_msg else None,
    )


def inputArrayTemplate(
    label,
    name,
    rows=3,
    cols=3,
    placeholder=None,
    values=None,
    error_msg=None,
    input_type="number",
    canValidateInline=False,
):
    # Normalize values to a rows x cols 2D list of strings
    total = rows * cols
    flat_vals = []
    if isinstance(values, list):
        # allow [[...], [...]] or flat list
        if values and isinstance(values[0], list):
            for r in range(rows):
                row_vals = values[r] if r < len(values) else []
                for c in range(cols):
                    v = row_vals[c] if c < len(row_vals) else ""
                    flat_vals.append(v)
        else:
            flat_vals = list(values)[:total] + [""] * max(0, total - len(values))
    else:
        flat_vals = [""] * total

    grid_style = (
        "display: grid; gap: 8px; "
        f"grid-template-columns: repeat({cols}, minmax(60px, 1fr)); max-width: 600px;"
    )
    # Build inputs row-major with names like <name>_r_c (1-based)
    inputs = []
    idx = 0
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            val = flat_vals[idx] if idx < len(flat_vals) else ""
            idx += 1
            inputs.append(
                Input(
                    name=f"{name.lower()}_{r}_{c}",
                    id=f"{name.lower()}_{r}_{c}",
                    placeholder=placeholder,
                    type=input_type,
                    value=val,
                    hx_post=f"/{name.lower()}" if canValidateInline else None,
                    style="width: 100%;",
                )
            )

    return Div(
        hx_target="this",
        hx_swap="outerHTML",
        cls=f"{error_msg if error_msg else 'Valid'}",
        style=control_container_style,
    )(
        labelDecoratorTemplate(Label(label), name in model_required_keys),
        Div(*inputs, style=grid_style),
        Div(f"{error_msg}", style="color: red;") if error_msg else None,
    )


def mk_opts(nm, cs, selected=None):
    return (
        Option(
            f"-- select {nm} --",
            disabled=True,
            selected=(selected is None),
            value="",
        ),
        *(
            Option(c, value=c, selected=(c == selected))
            for c in cs
        ),
    )


def selectEnumTemplate(
    label, options, name, hx_target=None, error_msg=None, canValidateInline=False, value=None
):
    return Div(
        hx_target="this",
        hx_swap="outerHTML",
        cls=f"{error_msg if error_msg else 'Valid'}",
        style=control_container_style,
    )(
        labelDecoratorTemplate(Label(label), name in model_required_keys),
        Select(
            *mk_opts(name, options, selected=value),
            name=name,
            id=name,
            hx_post=f"/{name.lower()}" if canValidateInline else None,
            hx_target=hx_target,
            style=select_input_style,
        ),
        Div(f"{error_msg}", style="color: red;") if error_msg else None,
    )


def mk_checkbox(options):
    return Div(style=control_container_style)(
        *[
            Div(CheckboxX(id=option, label=option), style="width: 100%;")
            for option in options
        ]
    )


def selectCheckboxTemplate(
    label, options, name, error_msg=None, canValidateInline=False
):
    return Div(
        hx_target="this",
        hx_swap="outerHTML",
        cls=f"{error_msg if error_msg else 'Valid'}",
        style=control_container_style,
    )(
        labelDecoratorTemplate(Label(label), name in model_required_keys),
        Group(
            mk_checkbox(options),
            name=name,
            id=name,
            hx_post=f"/{name.lower()}" if canValidateInline else None,
        ),
        Div(f"{error_msg}", style="color: red;") if error_msg else None,
    )


def trueFalseRadioTemplate(label, name, error_msg=None):
    return Div(
        labelDecoratorTemplate(Label(label), name in model_required_keys),
        Div(
            Input(type="radio", name=f"{name}", id=f"{name}_true", value="true"),
            Label("True", for_=f"{name}_true"),
            Input(type="radio", name=f"{name}", id=f"{name}_false", value="false"),
            Label("False", for_=f"{name}_false"),
            style="display: flex; flex-direction: row; align-items: center;",
        ),
        Div(f"{error_msg}", style="color: red;") if error_msg else None,
        style=f"{control_container_style} margin-bottom: 15px;",
    )


def relObjectTemplate(label, name, error_msg=None, href="", type_="", title=""):
    return Div(
        labelDecoratorTemplate(Label(label), name in model_required_keys),
        inputTemplate(
            label="href",
            name=f"{name}_href",
            val=href,
            placeholder="A link to the related object",
            input_type="text",
        ),
        inputTemplate(
            label="type",
            name=f"{name}_type",
            val=type_,
            placeholder="The media type of the related object",
            input_type="text",
        ),
        inputTemplate(
            label="title",
            name=f"{name}_title",
            val=title,
            placeholder="A descriptive title for the related object",
            input_type="text",
        ),
        Div(f"{error_msg}", style="color: red;") if error_msg else None,
        style=f"{control_container_style} margin-left: 15px;",
    )


def labelDecoratorTemplate(label, isRequired):
    required_indicator = Span("*", style="color: red; margin-right: 5px;")
    return Div(
        required_indicator if isRequired else None, label, style="display: flex;"
    )


def outputTemplate():
    return Div(
        Div(id="result", style=""),
        style="flex: 1 0 50%; overflow: auto; padding-left: 20px;",
    )


def prettyJsonTemplate(obj):
    return Div(
        Div(
            Pre(json.dumps(obj, indent=4), style="padding: 10px;"),
        ),
    )


def error_template(msg):
    return Div(
        msg,
        style="color: red; white-space: pre-wrap; margin-left: 10px; margin-bottom: 15px; text-indent: -10px;",
    )


copy_js_file_path = os.path.join(
    os.path.dirname(__file__), "js", "copy_to_clipboard.js"
)
copy_js = None
with open(copy_js_file_path, "r") as file:
    copy_js = file.read()


def copy_to_clipboard_button(item):
    return Button(
        "Copy JSON",
        style="margin-left: 10px; min-width: 120px;",
        onclick=copy_js,
        data_clipboard_text=(json.dumps(item, indent=2) if item else ""),
        disabled=(item is None),
    )


download_js_file_path = os.path.join(
    os.path.dirname(__file__), "js", "download_to_file.js"
)
download_js = None
with open(download_js_file_path, "r") as file:
    download_js = file.read()


def download_button(item):
    model_name = None
    if item:
        model_name = item.get("id") or item.get("title") or item.get("properties", {}).get("topo4d:data_type")
    return Button(
        "Download JSON",
        style="margin-left: 10px;",
        onclick=download_js,
        data_file_name=f"{model_name if model_name else 'item'}.json",
        data_file_content=(json.dumps(item, indent=2) if item else ""),
        disabled=(item is None),
    )


def button_bar(session):
    item = None
    d = session["stac_format_d"]
    if d:
        try:
            ml_model_metadata = construct_topo4d_properties(d)
            assets = construct_assets(d.get("assets"))
            item = create_pystac_item(
                ml_model_metadata,
                assets,
                geometry=d.get("geometry"),
                bbox=d.get("bbox"),
            )
        except:
            pass

    # Inline upload form as a button
    upload_form = Form(
        hx_post="/upload_las",
        hx_target="#result",
        hx_encoding="multipart/form-data",
        style="display: inline-block; margin-left: 10px;",
    )(
        Input(
            type="file",
            id="lasfile-input",
            name="lasfile",
            accept=".las,.laz",
            style="display:none;",
            onchange="this.form.requestSubmit()",
        ),
        Button(
            "Upload LAS/LAZ",
            type="button",
            onclick="document.getElementById('lasfile-input').click()",
        ),
    )

    return Div(
        Button(
            "Reset", hx_post="/clear_form", hx_target="#result", hx_swap="innerHTML"
        ),
        copy_to_clipboard_button(item),
        download_button(item),
        upload_form,
        id="button-bar",
        hx_swap_oob="#button_bar",
    )


def title_bar(title, session):
    return Div(
        H1(title),
        button_bar(session),
        style="display: flex; justify-content: space-between; align-items: center;",
    )


def tab_bar(selected):
    return Nav(
        Div(
            A(
                "Topo4D Form",
                href="/",
                _class="secondary" if selected == "/" else "contrast",
                style=tab_style["selected"]
                if selected == "/"
                else tab_style["unselected"],
                role="button",
            ),
            style=tab_wrapper_style,
        ),
        Div(
            A(
                "Asset Form",
                href="/asset",
                _class="secondary" if selected == "/asset" else "contrast",
                style=tab_style["selected"]
                if selected == "/asset"
                else tab_style["unselected"],
                role="button",
            ),
            style=tab_wrapper_style,
        ),
        Div(style=tab_spacer_style),
        style="justify-content: flex-start; margin: 15px 0;",
    )
