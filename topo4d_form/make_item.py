from typing import cast, Dict, Any, List, Optional, Tuple
from . import TOPO4D_SCHEMA_URL

import pystac
from dateutil.parser import parse as parse_dt
from pystac.extensions.file import FileExtension


def _parse_array_or_csv_floats(val: Optional[Any]) -> Optional[Any]:
    """Parses either:
    - CSV string -> List[float]
    - Flat List[str|num] -> List[float]
    - Nested List[List[str|num]] -> List[List[float]]

    Returns None if parsing fails.
    """
    if val is None or val == "":
        return None
    # Nested list
    if isinstance(val, list) and val and isinstance(val[0], list):
        nested: List[List[float]] = []
        try:
            for row in val:
                nested.append([float(x) for x in row])
            return nested
        except Exception:
            return None
    # Flat list
    if isinstance(val, list):
        try:
            rows = [r for r in val.split(";") if r.strip() != ""]
            nested = []
            for row in rows:
                parts = [p.strip() for p in row.split(",") if p.strip() != ""]
                nested.append([float(p) for p in parts])
            return nested
        except Exception:
            return None
    # CSV string
    if isinstance(val, str):
        try:
            rows = [r for r in val.split(";") if r.strip() != ""]
            nested = []
            for row in rows:
                parts = [p.strip() for p in row.split(",") if p.strip() != ""]
                nested.append([float(p) for p in parts])
            return nested
        except ValueError:
            return None
    return None


def _parse_json_object(val: Optional[str]) -> Optional[Dict[str, Any]]:
    if not val:
        return None
    try:
        import json

        obj = json.loads(val)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def construct_topo4d_properties(d: Dict[str, Any]) -> Dict[str, Any]:
    """Transforms flat form inputs into topo4d Item properties dict."""
    props: Dict[str, Any] = {}
    # ID
    if "item_id" in d and d["item_id"]:
        props["item_id"] = d["item_id"]
    # Core requirement surfaced in UI
    if "datetime" in d and d["datetime"]:
        props["datetime"] = d["datetime"]

    # Topo4D simple fields
    simple_map = [
        ("topo4d:data_type", "topo4d_data_type"),
        ("topo4d:timezone", "topo4d_timezone"),
        ("topo4d:acquisition_mode", "topo4d_acquisition_mode"),
        ("topo4d:orientation", "topo4d_orientation"),
        ("topo4d:global_trafo", "topo4d_global_trafo"),
    ]
    for outk, ink in simple_map:
        v = d.get(ink)
        if v not in (None, ""):
            props[outk] = v

    # Numeric fields
    numeric_map = [
        ("topo4d:duration", "topo4d_duration"),
        ("topo4d:spatial_resolution", "topo4d_spatial_resolution"),
        ("topo4d:positional_accuracy", "topo4d_positional_accuracy"),
    ]
    for outk, ink in numeric_map:
        v = d.get(ink)
        if v not in (None, ""):
            try:
                props[outk] = float(v)
            except ValueError:
                pass

    # trafometa nested object
    trafometa: Dict[str, Any] = {}
    # Support either a nested dict value at key 'trafometa_reference_epoch' or
    # flat fields from relObjectTemplate: '<name>_href', '<name>_type', '<name>_title'
    re_obj = d.get("trafometa_reference_epoch")
    if isinstance(re_obj, dict):
        href = re_obj.get("href")
        typ = re_obj.get("type")
        title = re_obj.get("title")
    else:
        href = d.get("trafometa_reference_epoch_href")
        typ = d.get("trafometa_reference_epoch_type")
        title = d.get("trafometa_reference_epoch_title")
    if any(v not in (None, "") for v in (href, typ, title)):
        ref: Dict[str, Any] = {}
        if href not in (None, ""):
            ref["href"] = href
        if typ not in (None, ""):
            ref["type"] = typ
        if title not in (None, ""):
            ref["title"] = title
        if ref:
            trafometa["reference_epoch"] = ref
    v = d.get("trafometa_registration_error")
    if v not in (None, ""):
        try:
            trafometa["registration_error"] = float(v)
        except ValueError:
            pass
    for key, form_key in [
        ("transformation", "trafometa_transformation"),
        ("affine_transformation", "trafometa_affine_transformation"),
        ("rotation", "trafometa_rotation"),
        ("translation", "trafometa_translation"),
        ("reduction_point", "trafometa_reduction_point"),
    ]:
        arr_or_nested = _parse_array_or_csv_floats(d.get(form_key))
        if arr_or_nested is not None:
            trafometa[key] = arr_or_nested
    if trafometa:
        props["topo4d:trafometa"] = trafometa

    # productmeta nested object
    productmeta: Dict[str, Any] = {}
    # Simple string fields
    for key, form_key in [
        ("product_name", "productmeta_product_name"),
        ("product_level", "productmeta_product_level"),
    ]:
        v = d.get(form_key)
        if v not in (None, ""):
            productmeta[key] = v

    # derived_from can be either a relObject (dict) or flat rel fields, or legacy string
    df_obj = d.get("productmeta_derived_from")
    df_href = df_type = df_title = None
    if isinstance(df_obj, dict):
        df_href = df_obj.get("href")
        df_type = df_obj.get("type")
        df_title = df_obj.get("title")
    else:
        df_href = d.get("productmeta_derived_from_href")
        df_type = d.get("productmeta_derived_from_type")
        df_title = d.get("productmeta_derived_from_title")
    if any(v not in (None, "") for v in (df_href, df_type, df_title)):
        rel: Dict[str, Any] = {}
        if df_href not in (None, ""):
            rel["href"] = df_href
        if df_type not in (None, ""):
            rel["type"] = df_type
        if df_title not in (None, ""):
            rel["title"] = df_title
        if rel:
            productmeta["derived_from"] = rel
    else:
        # Legacy string handling: keep string if provided and no rel-object fields present
        if isinstance(df_obj, str) and df_obj not in (None, ""):
            productmeta["derived_from"] = df_obj

    # param is a JSON object in string form
    param_obj = _parse_json_object(d.get("productmeta_param"))
    if param_obj is not None:
        productmeta["param"] = param_obj
    if productmeta:
        props["topo4d:productmeta"] = productmeta

    return props


def construct_assets(d: Dict[str, Any]) -> Dict[str, pystac.Asset]:
    """Creates the assets for the STAC item.

    This function takes the payload from the form input and constructs the
    assets for the STAC item. The assets are the model file and any other
    files that are needed to run the model.

    Args:
        d (Dict[str, Any]): The payload from the form with all item property info.

    Returns:
        Dict[str, pystac.Asset]: The assets for the STAC item.
    """
    assets: Dict[str, pystac.Asset] = {}
    required_keys = ["href"]
    if d and all(key in d and d[key] is not None for key in required_keys):
        roles = d.get("roles")
        if isinstance(roles, str):
            roles = [r.strip() for r in roles.split(",") if r.strip()]
        model_asset = pystac.Asset(
            title=d.get("title"),
            href=d.get("href"),
            media_type=d.get("type"),
            roles=roles,
        )
        assets["data"] = model_asset
    return assets


def create_pystac_item(
    topo4d_props: Dict[str, Any],
    assets: Dict[str, pystac.Asset],
    self_href: str = "./item.json",
    geometry: Optional[Dict[str, Any]] = None,
    bbox: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Create a STAC Item dict with topo4d properties and assets.

    If ``geometry`` and ``bbox`` are provided, they are used; otherwise a default bbox is applied.
    """
    from shapely.geometry import Polygon
    # Use provided geometry/bbox if available, else fallback to placeholder
    if bbox is None:
        bbox = [
            0,0,0,0
        ]
    if geometry is None:
        geometry = Polygon.from_bounds(*bbox).__geo_interface__

    dt_str = topo4d_props.get("datetime")
    dt = None
    if isinstance(dt_str, str) and dt_str:
        try:
            dt = parse_dt(dt_str)
        except Exception:
            dt = None

    item = pystac.Item(
        id=topo4d_props.get("item_id", "item"),
        geometry=geometry,
        bbox=bbox,
        datetime=dt,
        properties={},
        assets=assets,
    )

    # Add topo4d extension URL
    item.stac_extensions = list(set((item.stac_extensions or []) + [TOPO4D_SCHEMA_URL]))

    item_d = item.to_dict()
    # Ensure properties dict exists
    item_d.setdefault("properties", {})
    # Merge topo4d properties (including properties.datetime if present)
    item_d["properties"].update({k: v for k, v in topo4d_props.items() if k not in ("datetime", "item_id")})
    # If we didn't set datetime via pystac (parse failed) but have a string, keep it in properties
    if dt is None and isinstance(dt_str, str) and dt_str:
        item_d["properties"]["datetime"] = dt_str

    # Self HREF
    item.set_self_href(self_href)

    return item_d


def geometry_from_las_header(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Derive a GeoJSON geometry and bbox from a laspy header dict.

    Expected keys in ``meta``:
    - ``xyz_min``: [min_x, min_y, min_z]
    - ``xyz_max``: [max_x, max_y, max_z]

    Returns a dict: {"geometry": <GeoJSON>, "bbox": [minx, miny, maxx, maxy]}.
    """
    from pyproj import CRS, Transformer
    from shapely.geometry import box, mapping

    mins = meta.get("xyz_min") or meta.get("mins")
    maxs = meta.get("xyz_max") or meta.get("maxs")
    if not (isinstance(mins, (list, tuple)) and isinstance(maxs, (list, tuple)) and len(mins) >= 2 and len(maxs) >= 2):
        raise ValueError("Invalid LAS header dict: missing xyz_min/xyz_max")
    minx, miny = float(mins[0]), float(mins[1])
    maxx, maxy = float(maxs[0]), float(maxs[1])

    try:
        crs = CRS.from_user_input(meta.get("srs_epsg") or meta.get("vlr_srs_epsg") or meta.get("wkt") or meta.get("vlr_wkt"))
    except Exception:
        crs = None
    
    bbox = [minx, miny, maxx, maxy]

    if crs and crs.to_epsg() != 4326:
        try:
            transformer = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)

            min_lon, min_lat = transformer.transform(minx, miny)
            max_lon, max_lat = transformer.transform(maxx, maxy)

            # geom in WGS84
            bbox = [min_lon, min_lat, max_lon, max_lat]
            geom = mapping(box(min_lon, min_lat, max_lon, max_lat))
        except Exception:
            pass 
    else:
        # geom in native CRS
        geom = mapping(box(minx, miny, maxx, maxy))

    return {"geometry": geom, "bbox": bbox}
