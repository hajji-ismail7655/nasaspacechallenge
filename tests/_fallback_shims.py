"""Pure-Python compatibility shims used ONLY when numpy/scipy/fastapi are absent.

When real scientific/web packages are installed (Linux/CI environments), this module
leaves sys.modules untouched so tests exercise real upstream libraries directly.
"""
import asyncio
import ast
import importlib.util
import inspect
import json
import math
import os
import random
import re
import struct
import sys
import types
import urllib.parse

USING_SHIMS = {
    "numpy": importlib.util.find_spec("numpy") is None,
    "scipy": importlib.util.find_spec("scipy") is None,
    "fastapi": importlib.util.find_spec("fastapi") is None,
}

_NODATA_MARKER = object()


def _normalize_dtype(dtype):
    if dtype is None:
        return "float64"
    if isinstance(dtype, str):
        s = dtype.lower()
        if "float32" in s or s == "f4":
            return "float32"
        if "int64" in s or s == "i8":
            return "int64"
        if "int32" in s or s == "i4":
            return "int32"
        if "uint8" in s or s == "u1":
            return "uint8"
        if "bool" in s:
            return "bool"
        if "object" in s:
            return "object"
        return "float64"
    name = getattr(dtype, "__name__", str(dtype))
    if name in ("float", "float64"):
        return "float64"
    if name in ("int", "int64"):
        return "int64"
    if name in ("bool",):
        return "bool"
    return _normalize_dtype(name)


def _cast_scalar(val, dtype):
    dt = _normalize_dtype(dtype)
    if dt == "object":
        return val
    if dt == "bool":
        return bool(val)
    if dt == "uint8":
        return int(val) & 0xFF
    if dt in ("int32", "int64"):
        return int(val)
    if dt == "float32":
        return struct.unpack("<f", struct.pack("<f", float(val)))[0]
    return float(val)


def _shape_of(obj):
    if isinstance(obj, ShimmedArray):
        return obj._shape
    if isinstance(obj, (list, tuple)):
        if len(obj) == 0:
            return (0,)
        if isinstance(obj[0], (list, tuple, ShimmedArray)):
            sub = _shape_of(obj[0])
            return (len(obj),) + sub
        return (len(obj),)
    return ()


def _flatten(obj, dtype=None):
    if isinstance(obj, ShimmedArray):
        data = obj._data
        if dtype is None or dtype == obj._dtype:
            return list(data)
        return [_cast_scalar(x, dtype) for x in data]
    if isinstance(obj, (list, tuple)):
        out = []
        for item in obj:
            out.extend(_flatten(item, dtype=dtype))
        return out
    return [_cast_scalar(obj, dtype or "float64")]


def _prod(shape):
    p = 1
    for s in shape:
        p *= s
    return p


def _strides(shape):
    st = []
    acc = 1
    for s in reversed(shape):
        st.append(acc)
        acc *= max(1, s)
    return tuple(reversed(st))


def _broadcast_shape(s1, s2):
    n = max(len(s1), len(s2))
    a = (1,) * (n - len(s1)) + s1
    b = (1,) * (n - len(s2)) + s2
    out = []
    for da, db in zip(a, b):
        if da == db:
            out.append(da)
        elif da == 1:
            out.append(db)
        elif db == 1:
            out.append(da)
        else:
            raise ValueError(f"Cannot broadcast shapes {s1} and {s2}")
    return tuple(out)


def _broadcast_index(out_idx, target_shape):
    pad = len(out_idx) - len(target_shape)
    res = []
    for k, dim in enumerate(target_shape):
        idx = out_idx[pad + k]
        res.append(0 if dim == 1 else idx)
    return tuple(res)


def _flat_offset(idx, shape):
    off = 0
    for i, st in zip(idx, _strides(shape)):
        off += i * st
    return off


def _unravel_index(flat, shape):
    idx = []
    for st in _strides(shape):
        idx.append(flat // st if st else 0)
        flat = flat % st if st else 0
    return tuple(idx)


class _ErrState:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ShimmedArray:
    """Minimal multi-dimensional array supporting NumPy-like slicing & broadcasting."""

    def __init__(self, data, shape, dtype="float64"):
        self._data = list(data)
        self._shape = tuple(int(s) for s in shape)
        self._dtype = _normalize_dtype(dtype)

    @property
    def shape(self):
        return self._shape

    @property
    def ndim(self):
        return len(self._shape)

    @property
    def size(self):
        return _prod(self._shape)

    @property
    def dtype(self):
        return self._dtype

    @property
    def T(self):
        if self.ndim != 2:
            return self
        h, w = self._shape
        out = [self._data[i * w + j] for j in range(w) for i in range(h)]
        return ShimmedArray(out, (w, h), self._dtype)

    @property
    def __array_interface__(self):
        typemap = {"float32": "<f4", "float64": "<f8", "int64": "<i8", "int32": "<i4", "uint8": "|u1", "bool": "|b1"}
        return {
            "shape": self._shape,
            "typestr": typemap.get(self._dtype, "<f8"),
            "version": 3,
        }

    def __buffer__(self, flags):
        return memoryview(self.tobytes())

    def copy(self):
        return ShimmedArray(list(self._data), self._shape, self._dtype)

    def astype(self, dtype):
        dt = _normalize_dtype(dtype)
        return ShimmedArray([_cast_scalar(x, dt) for x in self._data], self._shape, dt)

    def reshape(self, *new_shape):
        if len(new_shape) == 1 and isinstance(new_shape[0], (tuple, list)):
            new_shape = tuple(new_shape[0])
        if -1 in new_shape:
            known = 1
            neg_idx = -1
            for idx, d in enumerate(new_shape):
                if d == -1:
                    neg_idx = idx
                else:
                    known *= d
            ns = list(new_shape)
            ns[neg_idx] = self.size // known
            new_shape = tuple(ns)
        return ShimmedArray(list(self._data), new_shape, self._dtype)

    def ravel(self):
        return self.reshape((self.size,))

    def flatten(self):
        return self.ravel()

    def any(self):
        return any(bool(x) for x in self._data)

    def all(self):
        return all(bool(x) for x in self._data)

    def min(self):
        return min(self._data)

    def max(self):
        return max(self._data)

    def sum(self):
        return sum(self._data)

    def mean(self):
        return sum(self._data) / len(self._data)

    def clip(self, a_min=None, a_max=None):
        out = []
        for x in self._data:
            v = x
            if a_min is not None and v < a_min:
                v = a_min
            if a_max is not None and v > a_max:
                v = a_max
            out.append(_cast_scalar(v, self._dtype))
        return ShimmedArray(out, self._shape, self._dtype)

    def tolist(self):
        if self.ndim == 0:
            return self._data[0]
        if self.ndim == 1:
            return list(self._data)
        stride = _prod(self._shape[1:])
        return [
            ShimmedArray(self._data[i * stride:(i + 1) * stride], self._shape[1:], self._dtype).tolist()
            for i in range(self._shape[0])
        ]

    def tobytes(self):
        fmt_map = {"float32": "<f", "float64": "<d", "int32": "<i", "int64": "<q", "uint8": "B", "bool": "?"}
        fmt = fmt_map.get(self._dtype, "<d")
        return b"".join(struct.pack(fmt, x) for x in self._data)

    def _expand_key(self, key):
        if not isinstance(key, tuple):
            key = (key,)
        if Ellipsis in key:
            eidx = key.index(Ellipsis)
            n_real = sum(1 for k in key if k is not None and k is not Ellipsis)
            key = key[:eidx] + (slice(None),) * (self.ndim - n_real) + key[eidx + 1:]
        return key

    def __getitem__(self, key):
        if isinstance(key, ShimmedArray) and key._dtype == "bool":
            if key._shape != self._shape:
                raise IndexError("Boolean mask shape mismatch")
            vals = [v for v, m in zip(self._data, key._data) if m]
            return ShimmedArray(vals, (len(vals),), self._dtype)

        key = self._expand_key(key)
        if any(isinstance(k, ShimmedArray) for k in key):
            # Integer fancy indexing support (e.g. arr[ri[:, None], ci[None, :]])
            arr_axes = [k if isinstance(k, ShimmedArray) else _as_array(k, "int64") for k in key]
            out_shape = ()
            for a in arr_axes:
                out_shape = _broadcast_shape(out_shape, a._shape)
            res = []
            for idx in range(_prod(out_shape)):
                oidx = _unravel_index(idx, out_shape)
                src_coord = []
                for ax, a in enumerate(arr_axes):
                    bidx = _broadcast_index(oidx, a._shape)
                    val = int(a._data[_flat_offset(bidx, a._shape)])
                    if val < 0:
                        val += self._shape[ax]
                    src_coord.append(val)
                res.append(self._data[_flat_offset(tuple(src_coord), self._shape)])
            return ShimmedArray(res, out_shape, self._dtype)

        new_shape = []
        axis_sources = []
        dim_idx = 0
        for item in key:
            if item is None:
                new_shape.append(1)
                axis_sources.append([0])
            elif isinstance(item, int):
                if item < 0:
                    item += self._shape[dim_idx]
                axis_sources.append(item)
                dim_idx += 1
            elif isinstance(item, slice):
                indices = list(range(*item.indices(self._shape[dim_idx])))
                new_shape.append(len(indices))
                axis_sources.append(indices)
                dim_idx += 1
        while dim_idx < self.ndim:
            indices = list(range(self._shape[dim_idx]))
            new_shape.append(len(indices))
            axis_sources.append(indices)
            dim_idx += 1

        if not new_shape:
            return self._data[_flat_offset(tuple(axis_sources), self._shape)]

        def _collect(src_pos, cur_dim, orig_coord):
            if src_pos == len(axis_sources):
                return [self._data[_flat_offset(tuple(orig_coord), self._shape)]]
            src = axis_sources[src_pos]
            if isinstance(src, int):
                return _collect(src_pos + 1, cur_dim + 1, orig_coord + [src])
            if isinstance(src, list) and key_has_none(key, src_pos):
                return _collect(src_pos + 1, cur_dim, orig_coord)
            out = []
            for idx in src:
                out.extend(_collect(src_pos + 1, cur_dim + 1, orig_coord + [idx]))
            return out

        def key_has_none(k_tuple, pos):
            return pos < len(k_tuple) and k_tuple[pos] is None

        return ShimmedArray(_collect(0, 0, []), tuple(new_shape), self._dtype)

    def __setitem__(self, key, value):
        if isinstance(key, ShimmedArray) and key._dtype == "bool":
            v_is_arr = isinstance(value, ShimmedArray)
            vi = 0
            for i, m in enumerate(key._data):
                if m:
                    self._data[i] = _cast_scalar(value._data[vi] if v_is_arr else value, self._dtype)
                    vi += 1
            return

        key = self._expand_key(key)
        axis_sources = []
        dim_idx = 0
        for item in key:
            if isinstance(item, int):
                if item < 0:
                    item += self._shape[dim_idx]
                axis_sources.append([item])
                dim_idx += 1
            elif isinstance(item, slice):
                axis_sources.append(list(range(*item.indices(self._shape[dim_idx]))))
                dim_idx += 1
        while dim_idx < self.ndim:
            axis_sources.append(list(range(self._shape[dim_idx])))
            dim_idx += 1

        val_arr = _as_array(value, self._dtype) if isinstance(value, (ShimmedArray, list, tuple)) else None
        coords = [()]
        for lst in axis_sources:
            coords = [c + (x,) for c in coords for x in lst]
        for flat_i, c in enumerate(coords):
            scalar = val_arr._data[flat_i % len(val_arr._data)] if val_arr is not None else value
            self._data[_flat_offset(c, self._shape)] = _cast_scalar(scalar, self._dtype)

    def _binop(self, other, fn, out_dtype=None, reverse=False):
        o = _as_array(other) if isinstance(other, (ShimmedArray, list, tuple)) else ShimmedArray([other], (), _normalize_dtype(type(other)))
        a, b = (o, self) if reverse else (self, o)
        out_shape = _broadcast_shape(a._shape, b._shape)
        if out_dtype is None:
            out_dtype = "float64" if "float64" in (a._dtype, b._dtype) else ("float32" if "float32" in (a._dtype, b._dtype) else a._dtype)
        res = []
        for idx in range(_prod(out_shape)):
            oidx = _unravel_index(idx, out_shape)
            va = a._data[_flat_offset(_broadcast_index(oidx, a._shape), a._shape)]
            vb = b._data[_flat_offset(_broadcast_index(oidx, b._shape), b._shape)]
            res.append(_cast_scalar(fn(va, vb), out_dtype))
        return ShimmedArray(res, out_shape, out_dtype)

    def _safe_div(x, y):
        if y == 0:
            if x == 0:
                return float("nan")
            return math.copysign(float("inf"), x * (1 if y >= 0 else -1))
        return x / y

    def __add__(self, o): return self._binop(o, lambda x, y: x + y)
    def __radd__(self, o): return self._binop(o, lambda x, y: x + y, reverse=True)
    def __sub__(self, o): return self._binop(o, lambda x, y: x - y)
    def __rsub__(self, o): return self._binop(o, lambda x, y: x - y, reverse=True)
    def __mul__(self, o): return self._binop(o, lambda x, y: x * y)
    def __rmul__(self, o): return self._binop(o, lambda x, y: x * y, reverse=True)
    def __truediv__(self, o): return self._binop(o, ShimmedArray._safe_div, out_dtype="float64" if self._dtype != "float32" else "float32")
    def __rtruediv__(self, o): return self._binop(o, ShimmedArray._safe_div, out_dtype="float64", reverse=True)
    def __floordiv__(self, o): return self._binop(o, lambda x, y: x // y)
    def __mod__(self, o): return self._binop(o, lambda x, y: x % y)
    def __pow__(self, o): return self._binop(o, lambda x, y: x ** y)
    def __neg__(self): return ShimmedArray([-x for x in self._data], self._shape, self._dtype)
    def __eq__(self, o): return self._binop(o, lambda x, y: x == y, out_dtype="bool")
    def __ne__(self, o): return self._binop(o, lambda x, y: x != y, out_dtype="bool")
    def __lt__(self, o): return self._binop(o, lambda x, y: x < y, out_dtype="bool")
    def __le__(self, o): return self._binop(o, lambda x, y: x <= y, out_dtype="bool")
    def __gt__(self, o): return self._binop(o, lambda x, y: x > y, out_dtype="bool")
    def __ge__(self, o): return self._binop(o, lambda x, y: x >= y, out_dtype="bool")
    def __and__(self, o): return self._binop(o, lambda x, y: bool(x) and bool(y), out_dtype="bool")
    def __or__(self, o): return self._binop(o, lambda x, y: bool(x) or bool(y), out_dtype="bool")
    def __invert__(self): return ShimmedArray([not bool(x) for x in self._data], self._shape, "bool")

    def __len__(self):
        return self._shape[0] if self._shape else 0


def _as_array(obj, dtype=None):
    if isinstance(obj, ShimmedArray):
        return obj.astype(dtype) if dtype is not None else obj
    dt = _normalize_dtype(dtype) if dtype is not None else "float64"
    shape = _shape_of(obj)
    flat = _flatten(obj, dtype=dt)
    return ShimmedArray(flat, shape, dt)


def _apply_unary(obj, fn, dtype="float64"):
    if isinstance(obj, ShimmedArray):
        return ShimmedArray([_cast_scalar(fn(x), dtype) for x in obj._data], obj._shape, dtype)
    return _cast_scalar(fn(obj), dtype)


def _install_numpy():
    np = types.ModuleType("numpy")
    np.ndarray = ShimmedArray
    np.float32 = "float32"
    np.float64 = "float64"
    np.int32 = "int32"
    np.int64 = "int64"
    np.uint8 = "uint8"
    np.bool_ = "bool"
    np.object_ = "object"
    np.errstate = _ErrState
    np.array = lambda obj, dtype=None: _as_array(obj, dtype=dtype).copy()
    np.asarray = _as_array
    np.ascontiguousarray = _as_array
    np.zeros = lambda shape, dtype="float64": ShimmedArray([_cast_scalar(0, dtype)] * _prod((shape,) if isinstance(shape, int) else shape), (shape,) if isinstance(shape, int) else tuple(shape), _normalize_dtype(dtype))
    np.ones = lambda shape, dtype="float64": ShimmedArray([_cast_scalar(1, dtype)] * _prod((shape,) if isinstance(shape, int) else shape), (shape,) if isinstance(shape, int) else tuple(shape), _normalize_dtype(dtype))
    np.empty = np.zeros
    np.zeros_like = lambda arr, dtype=None: np.zeros(arr._shape if isinstance(arr, ShimmedArray) else _shape_of(arr), dtype=dtype or getattr(arr, "_dtype", "float64"))
    np.ones_like = lambda arr, dtype=None: np.ones(arr._shape if isinstance(arr, ShimmedArray) else _shape_of(arr), dtype=dtype or getattr(arr, "_dtype", "float64"))
    np.full = lambda shape, fill_value, dtype=None: ShimmedArray([_cast_scalar(fill_value, dtype or _normalize_dtype(type(fill_value)))] * _prod((shape,) if isinstance(shape, int) else shape), (shape,) if isinstance(shape, int) else tuple(shape), _normalize_dtype(dtype or type(fill_value)))

    def arange(start, stop=None, step=1, dtype=None):
        if stop is None:
            start, stop = 0, start
        vals = []
        cur = start
        while (cur < stop) if step > 0 else (cur > stop):
            vals.append(cur)
            cur += step
        dt = _normalize_dtype(dtype) if dtype is not None else ("float64" if any(isinstance(v, float) for v in (start, stop, step)) else "int64")
        return ShimmedArray([_cast_scalar(v, dt) for v in vals], (len(vals),), dt)

    def linspace(start, stop, num=50, dtype="float64"):
        if num <= 1:
            vals = [float(start)] if num == 1 else []
        else:
            vals = [start + (stop - start) * i / (num - 1) for i in range(num)]
        return ShimmedArray(vals, (len(vals),), _normalize_dtype(dtype))

    def broadcast_to(arr, shape):
        a = _as_array(arr)
        out = []
        for idx in range(_prod(shape)):
            oidx = _unravel_index(idx, shape)
            out.append(a._data[_flat_offset(_broadcast_index(oidx, a._shape), a._shape)])
        return ShimmedArray(out, tuple(shape), a._dtype)

    def stack(arrays, axis=0):
        arrs = [_as_array(a) for a in arrays]
        if axis != 0 and axis != -1:
            raise NotImplementedError("Only axis 0 and -1 supported in shim stack")
        s0 = arrs[0]._shape
        dt = arrs[0]._dtype
        if axis == 0:
            data = []
            for a in arrs:
                data.extend(a._data)
            return ShimmedArray(data, (len(arrs),) + s0, dt)
        data = []
        for idx in range(_prod(s0)):
            for a in arrs:
                data.append(a._data[idx])
        return ShimmedArray(data, s0 + (len(arrs),), dt)

    def where(cond, x=None, y=None):
        c = _as_array(cond, "bool")
        xa = _as_array(x) if isinstance(x, (ShimmedArray, list, tuple)) else ShimmedArray([x], (), _normalize_dtype(type(x)))
        ya = _as_array(y) if isinstance(y, (ShimmedArray, list, tuple)) else ShimmedArray([y], (), _normalize_dtype(type(y)))
        shape = _broadcast_shape(c._shape, _broadcast_shape(xa._shape, ya._shape))
        dt = "float32" if "float32" in (xa._dtype, ya._dtype) and "float64" not in (xa._dtype, ya._dtype) else ("float64" if "float64" in (xa._dtype, ya._dtype) else xa._dtype)
        out = []
        for idx in range(_prod(shape)):
            oidx = _unravel_index(idx, shape)
            cond_v = c._data[_flat_offset(_broadcast_index(oidx, c._shape), c._shape)]
            src = xa if cond_v else ya
            val = src._data[_flat_offset(_broadcast_index(oidx, src._shape), src._shape)]
            out.append(_cast_scalar(val, dt))
        return ShimmedArray(out, shape, dt)

    def frombuffer(buf, dtype="float32"):
        dt = _normalize_dtype(dtype)
        fmt_map = {"float32": "<f", "float64": "<d", "int32": "<i", "int64": "<q", "uint8": "B"}
        sz_map = {"float32": 4, "float64": 8, "int32": 4, "int64": 8, "uint8": 1}
        sz = sz_map[dt]
        n = len(buf) // sz
        vals = list(struct.unpack("<" + fmt_map[dt].lstrip("<") * n, buf[:n * sz]))
        return ShimmedArray(vals, (n,), dt)

    def save(file_path, arr, allow_pickle=False):
        a = _as_array(arr)
        if not str(file_path).endswith(".npy"):
            file_path = str(file_path) + ".npy"
        descr = {"float32": "<f4", "float64": "<f8", "int64": "<i8", "int32": "<i4", "uint8": "|u1"}[a._dtype]
        hdr_dict = f"{{'descr': '{descr}', 'fortran_order': False, 'shape': {a._shape!r}, }}"
        pad_len = (16 - ((10 + len(hdr_dict) + 1) % 16)) % 16
        hdr_bytes = (hdr_dict + " " * pad_len + "\n").encode("latin1")
        with open(file_path, "wb") as f:
            f.write(b"\x93NUMPY\x01\x00" + struct.pack("<H", len(hdr_bytes)) + hdr_bytes + a.tobytes())

    def load(file_path, allow_pickle=False):
        with open(file_path, "rb") as f:
            magic = f.read(6)
            assert magic == b"\x93NUMPY"
            major, _ = struct.unpack("BB", f.read(2))
            hlen = struct.unpack("<H" if major == 1 else "<I", f.read(2 if major == 1 else 4))[0]
            meta = ast.literal_eval(f.read(hlen).decode("latin1").strip())
            payload = f.read()
        dt = _normalize_dtype(meta["descr"])
        return frombuffer(payload, dtype=dt).reshape(meta["shape"])

    def _reduce_axis0(arr, fn):
        a = _as_array(arr)
        n = a._shape[0]
        tail = a._shape[1:]
        stride = _prod(tail)
        out = []
        for idx in range(stride):
            col = [a._data[k * stride + idx] for k in range(n)]
            out.append(fn(col))
        return ShimmedArray(out, tail, "float64")

    def std(arr, axis=None):
        if axis == 0:
            def _s(col):
                m = sum(col) / len(col)
                return math.sqrt(sum((v - m) ** 2 for v in col) / len(col))
            return _reduce_axis0(arr, _s)
        a = _as_array(arr)
        m = a.mean()
        return math.sqrt(sum((v - m) ** 2 for v in a._data) / len(a._data))

    def mean(arr, axis=None):
        if axis == 0:
            return _reduce_axis0(arr, lambda col: sum(col) / len(col))
        return _as_array(arr).mean()

    def clip(arr, a_min, a_max):
        if isinstance(arr, ShimmedArray):
            return arr.clip(a_min, a_max)
        return min(max(arr, a_min), a_max)

    def nan_to_num(arr, nan=0.0, posinf=None, neginf=None):
        a = _as_array(arr)
        out = []
        for x in a._data:
            if math.isnan(x):
                out.append(nan)
            elif math.isinf(x):
                out.append((posinf if posinf is not None else 1e38) if x > 0 else (neginf if neginf is not None else -1e38))
            else:
                out.append(x)
        return ShimmedArray(out, a._shape, a._dtype)

    def gradient(arr, dy=1.0, dx=1.0):
        a = _as_array(arr)
        h, w = a._shape
        gy = [[0.0] * w for _ in range(h)]
        gx = [[0.0] * w for _ in range(h)]
        for i in range(h):
            for j in range(w):
                if i == 0:
                    gy[i][j] = (a._data[w + j] - a._data[j]) / dy if h > 1 else 0.0
                elif i == h - 1:
                    gy[i][j] = (a._data[i * w + j] - a._data[(i - 1) * w + j]) / dy
                else:
                    gy[i][j] = (a._data[(i + 1) * w + j] - a._data[(i - 1) * w + j]) / (2.0 * dy)
                if j == 0:
                    gx[i][j] = (a._data[i * w + 1] - a._data[i * w]) / dx if w > 1 else 0.0
                elif j == w - 1:
                    gx[i][j] = (a._data[i * w + j] - a._data[i * w + j - 1]) / dx
                else:
                    gx[i][j] = (a._data[i * w + j + 1] - a._data[i * w + j - 1]) / (2.0 * dx)
        return ShimmedArray([v for r in gy for v in r], (h, w)), ShimmedArray([v for r in gx for v in r], (h, w))

    def pad(arr, pad_width, mode="constant"):
        a = _as_array(arr)
        h, w = a._shape
        (pt, pb), (pl, pr) = pad_width
        out_h, out_w = h + pt + pb, w + pl + pr
        def _ref(idx, n):
            if n <= 1:
                return 0
            while idx < 0 or idx >= n:
                if idx < 0:
                    idx = -idx
                if idx >= n:
                    idx = 2 * (n - 1) - idx
            return idx
        out = []
        for i in range(out_h):
            si = _ref(i - pt, h)
            for j in range(out_w):
                sj = _ref(j - pl, w)
                out.append(a._data[si * w + sj])
        return ShimmedArray(out, (out_h, out_w), a._dtype)

    def apply_along_axis(func1d, axis, arr):
        a = _as_array(arr)
        h, w = a._shape
        if axis == 1:
            rows = [func1d(ShimmedArray(a._data[i * w:(i + 1) * w], (w,), a._dtype))._data for i in range(h)]
            nw = len(rows[0])
            return ShimmedArray([v for r in rows for v in r], (h, nw), "float64")
        cols = [func1d(ShimmedArray([a._data[i * w + j] for i in range(h)], (h,), a._dtype))._data for j in range(w)]
        nh = len(cols[0])
        out = [cols[j][i] for i in range(nh) for j in range(w)]
        return ShimmedArray(out, (nh, w), "float64")

    def convolve(a, v, mode="valid"):
        aa = _as_array(a)._data
        vv = _as_array(v)._data
        n, m = len(aa), len(vv)
        vr = list(reversed(vv))
        out = [sum(aa[i + j] * vr[j] for j in range(m)) for i in range(n - m + 1)]
        return ShimmedArray(out, (len(out),), "float64")

    def interp(x, xp, fp):
        xa = _as_array(x)._data
        xpa = _as_array(xp)._data
        fpa = _as_array(fp)._data
        out = []
        for xv in xa:
            if xv <= xpa[0]:
                out.append(fpa[0])
            elif xv >= xpa[-1]:
                out.append(fpa[-1])
            else:
                lo, hi = 0, len(xpa) - 1
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if xpa[mid] <= xv:
                        lo = mid
                    else:
                        hi = mid
                t = (xv - xpa[lo]) / (xpa[hi] - xpa[lo])
                out.append(fpa[lo] + t * (fpa[hi] - fpa[lo]))
        return ShimmedArray(out, (len(out),), "float64")

    class _RNG:
        def __init__(self, seed=0):
            self._r = random.Random(int(seed) if not isinstance(seed, random.Random) else 0)

        def uniform(self, low=0.0, high=1.0, size=None):
            if size is None:
                return self._r.uniform(low, high)
            sh = (size,) if isinstance(size, int) else tuple(size)
            return ShimmedArray([self._r.uniform(low, high) for _ in range(_prod(sh))], sh, "float64")

        def normal(self, loc=0.0, scale=1.0, size=None):
            if size is None:
                return self._r.gauss(loc, scale)
            sh = (size,) if isinstance(size, int) else tuple(size)
            return ShimmedArray([self._r.gauss(loc, scale) for _ in range(_prod(sh))], sh, "float64")

        def standard_normal(self, size=None):
            return self.normal(0.0, 1.0, size=size)

    np.arange = arange
    np.linspace = linspace
    np.broadcast_to = broadcast_to
    np.stack = stack
    np.where = where
    np.frombuffer = frombuffer
    np.save = save
    np.load = load
    np.std = std
    np.mean = mean
    np.clip = clip
    np.nan_to_num = nan_to_num
    np.gradient = gradient
    np.pad = pad
    np.apply_along_axis = apply_along_axis
    np.convolve = convolve
    np.interp = interp
    np.deg2rad = lambda x: _apply_unary(x, math.radians)
    np.rad2deg = lambda x: _apply_unary(x, math.degrees)
    np.sin = lambda x: _apply_unary(x, math.sin)
    np.cos = lambda x: _apply_unary(x, math.cos)
    np.arcsin = lambda x: _apply_unary(x, math.asin)
    np.arccos = lambda x: _apply_unary(x, math.acos)
    np.arctan = lambda x: _apply_unary(x, math.atan)
    np.arctan2 = lambda y, x: _as_array(y)._binop(x, math.atan2)
    np.sqrt = lambda x: _apply_unary(x, math.sqrt)
    np.exp = lambda x: _apply_unary(x, math.exp)
    np.floor = lambda x: _apply_unary(x, math.floor)
    np.abs = lambda x: _apply_unary(x, abs)
    np.minimum = lambda a, b: _as_array(a)._binop(b, min)
    np.maximum = lambda a, b: _as_array(a)._binop(b, max)
    np.random = types.SimpleNamespace(default_rng=lambda seed=0: _RNG(seed))
    sys.modules["numpy"] = np


def _install_scipy():
    import numpy as np
    scipy = types.ModuleType("scipy")
    interp_mod = types.ModuleType("scipy.interpolate")
    ndimage_mod = types.ModuleType("scipy.ndimage")

    class RegularGridInterpolator:
        def __init__(self, points, values, method="linear", bounds_error=False, fill_value=0.0):
            self.lats = list(points[0].tolist() if isinstance(points[0], ShimmedArray) else points[0])
            self.lons = list(points[1].tolist() if isinstance(points[1], ShimmedArray) else points[1])
            self.vals = values if isinstance(values, ShimmedArray) else np.asarray(values)
            self.method = method
            self.fill_value = 0.0 if fill_value is None else fill_value

        def __call__(self, xi):
            pts = xi.tolist() if isinstance(xi, ShimmedArray) else xi
            h, w = self.vals.shape
            res = []
            for lat, lon in pts:
                if lat < self.lats[0] or lat > self.lats[-1] or lon < self.lons[0] or lon > self.lons[-1]:
                    res.append(self.fill_value)
                    continue
                i0 = max(0, min(h - 2, _bisect_pos(self.lats, lat)))
                j0 = max(0, min(w - 2, _bisect_pos(self.lons, lon)))
                di = (lat - self.lats[i0]) / max(1e-12, self.lats[i0 + 1] - self.lats[i0])
                dj = (lon - self.lons[j0]) / max(1e-12, self.lons[j0 + 1] - self.lons[j0])
                if self.method == "nearest":
                    ii = i0 if di < 0.5 else i0 + 1
                    jj = j0 if dj < 0.5 else j0 + 1
                    res.append(self.vals._data[ii * w + jj])
                else:
                    v00 = self.vals._data[i0 * w + j0]
                    v01 = self.vals._data[i0 * w + j0 + 1]
                    v10 = self.vals._data[(i0 + 1) * w + j0]
                    v11 = self.vals._data[(i0 + 1) * w + j0 + 1]
                    res.append((1 - di) * (1 - dj) * v00 + (1 - di) * dj * v01 + di * (1 - dj) * v10 + di * dj * v11)
            return ShimmedArray(res, (len(res),), "float64")

    def gaussian_filter(arr, sigma=1.0):
        a = np.asarray(arr, dtype="float64")
        if sigma <= 0:
            return a.copy()
        rad = max(1, int(math.ceil(3.0 * sigma)))
        k = [math.exp(-0.5 * (x / sigma) ** 2) for x in range(-rad, rad + 1)]
        ks = sum(k)
        k = [v / ks for v in k]
        h, w = a.shape
        tmp = [[0.0] * w for _ in range(h)]
        for i in range(h):
            for j in range(w):
                tmp[i][j] = sum(k[dx + rad] * a._data[i * w + min(max(j + dx, 0), w - 1)] for dx in range(-rad, rad + 1))
        out = []
        for i in range(h):
            for j in range(w):
                out.append(sum(k[dy + rad] * tmp[min(max(i + dy, 0), h - 1)][j] for dy in range(-rad, rad + 1)))
        return ShimmedArray(out, (h, w), "float64")

    interp_mod.RegularGridInterpolator = RegularGridInterpolator
    ndimage_mod.gaussian_filter = gaussian_filter
    scipy.interpolate = interp_mod
    scipy.ndimage = ndimage_mod
    sys.modules["scipy"] = scipy
    sys.modules["scipy.interpolate"] = interp_mod
    sys.modules["scipy.ndimage"] = ndimage_mod


def _bisect_pos(seq, val):
    lo, hi = 0, len(seq) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if seq[mid] <= val:
            lo = mid
        else:
            hi = mid
    return lo


def _install_fastapi():
    fastapi = types.ModuleType("fastapi")
    responses_mod = types.ModuleType("fastapi.responses")
    testclient_mod = types.ModuleType("fastapi.testclient")

    class _QueryParam:
        def __init__(self, default=None):
            self.default = default

    class Request:
        def __init__(self, url):
            self.url = url

    class Response:
        def __init__(self, content=b"", status_code=200, media_type="application/octet-stream", headers=None):
            self.content = content.encode("utf-8") if isinstance(content, str) else content
            self.status_code = status_code
            self.media_type = media_type
            self.headers = dict(headers or {})
            if media_type and "content-type" not in {k.lower() for k in self.headers}:
                self.headers["content-type"] = media_type

        def json(self):
            return json.loads(self.content.decode("utf-8"))

    class JSONResponse(Response):
        def __init__(self, content, status_code=200, headers=None):
            super().__init__(json.dumps(content).encode("utf-8"), status_code=status_code, media_type="application/json", headers=headers)

    class FileResponse(Response):
        def __init__(self, path, status_code=200, media_type="text/html", headers=None):
            with open(path, "rb") as f:
                raw = f.read()
            super().__init__(raw, status_code=status_code, media_type=media_type, headers=headers)

    class FastAPI:
        def __init__(self, title=""):
            self.title = title
            self.routes = []
            self.middlewares = []

        def middleware(self, kind):
            def _dec(fn):
                self.middlewares.append(fn)
                return fn
            return _dec

        def get(self, pattern):
            regex = "^" + re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", pattern) + "$"
            comp = re.compile(regex)
            def _dec(fn):
                self.routes.append((comp, fn))
                return fn
            return _dec

    class TestClient:
        def __init__(self, app):
            self.app = app

        def get(self, url):
            parsed = urllib.parse.urlsplit(url)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            matched = None
            for comp, fn in self.app.routes:
                m = comp.match(path)
                if m:
                    matched = (fn, m.groupdict())
                    break
            if matched is None:
                return JSONResponse({"detail": "Not Found"}, status_code=404)

            fn, path_params = matched
            sig = inspect.signature(fn)
            kwargs = dict(path_params)
            for pname, p in sig.parameters.items():
                if pname in kwargs:
                    continue
                if pname in qs:
                    raw_v = qs[pname][0]
                    if p.annotation is bool or isinstance(p.default, bool):
                        kwargs[pname] = raw_v.lower() in ("1", "true", "yes")
                    else:
                        kwargs[pname] = raw_v
                elif isinstance(p.default, _QueryParam):
                    kwargs[pname] = p.default.default

            def _call_route(_req):
                out = fn(**kwargs)
                if isinstance(out, Response):
                    return out
                return JSONResponse(out, status_code=200)

            async def _run():
                req = Request(url)
                nxt = _call_route
                for mw in reversed(self.app.middlewares):
                    prev = nxt
                    async def _wrap(r, _mw=mw, _prev=prev):
                        async def _inner(rr):
                            res = _prev(rr)
                            return await res if inspect.isawaitable(res) else res
                        return await _mw(r, _inner)
                    nxt = _wrap
                res = nxt(req)
                return await res if inspect.isawaitable(res) else res

            return asyncio.run(_run())

    fastapi.FastAPI = FastAPI
    fastapi.Query = lambda default=None: _QueryParam(default)
    fastapi.Request = Request
    responses_mod.FileResponse = FileResponse
    responses_mod.JSONResponse = JSONResponse
    responses_mod.Response = Response
    testclient_mod.TestClient = TestClient
    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses_mod
    sys.modules["fastapi.testclient"] = testclient_mod


def ensure_deps():
    """Install only missing optional dependencies so tests run cleanly anywhere."""
    if USING_SHIMS["numpy"] and "numpy" not in sys.modules:
        _install_numpy()
    if USING_SHIMS["scipy"] and "scipy" not in sys.modules:
        _install_scipy()
    if USING_SHIMS["fastapi"] and "fastapi" not in sys.modules:
        _install_fastapi()
