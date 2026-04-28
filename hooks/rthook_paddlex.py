# PyInstaller runtime hook: 在程序启动时修补 paddlex/pandas 的导入
# 解决 paddlex 依赖 pandas、导致整个 pandas 生态链被拉进来的问题

import sys

def _patch_paddlex():
    """修补 paddlex，使 pyinstaller 能正常打包"""
    import types

    # 为 pyinstaller 构造一个轻量级的 pandas 替代品
    fake_pandas = types.ModuleType('pandas')
    fake_pandas.__version__ = '2.0.0'

    # DataFrame / Series / Index 等基础类型
    class FakeDataFrame:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, item):
            return lambda *a, **kw: FakeDataFrame()

    class FakeSeries:
        def __init__(self, *args, **kwargs):
            pass

    class FakeIndex:
        def __init__(self, *args, **kwargs):
            pass

    class FakeDataFrameGroupBy:
        def __getattr__(self, item):
            return lambda *a, **kw: FakeDataFrame()

    class FakeSeriesGroupBy:
        def __init__(self, *args, **kwargs):
            pass

    class FakeNDFrame:
        pass

    fake_pandas.DataFrame = FakeDataFrame
    fake_pandas.Series = FakeSeries
    fake_pandas.Index = FakeIndex
    fake_pandas.DataFrameGroupBy = FakeDataFrameGroupBy
    fake_pandas.SeriesGroupBy = FakeSeriesGroupBy
    fake_pandas.DataFrameGroupBy = FakeDataFrameGroupBy
    fake_pandas.core = types.ModuleType('pandas.core')
    fake_pandas.core.frame = types.ModuleType('pandas.core.frame')
    fake_pandas.core.frame.DataFrame = FakeDataFrame
    fake_pandas.core.series = types.ModuleType('pandas.core.series')
    fake_pandas.core.series.Series = FakeSeries
    fake_pandas.errors = types.ModuleType('pandas.errors')
    fake_pandas.errors.EmptyDataError = type('EmptyDataError', (Exception,), {})
    fake_pandas.errors.ParserError = type('ParserError', (Exception,), {})
    fake_pandas._testing = types.ModuleType('pandas._testing')
    fake_pandas._testing.assert_frame_equal = lambda *a, **kw: None
    fake_pandas.io = types.ModuleType('pandas.io')
    fake_pandas.io.formats = types.ModuleType('pandas.io.formats')
    fake_pandas.io.formats.style = types.ModuleType('pandas.io.formats.style')
    fake_pandas.plotting = types.ModuleType('pandas.plotting')
    fake_pandas.plotting.register_matplotlib_converters = lambda: None
    fake_pandas.plotting.deregister_matplotlib_converters = lambda: None
    fake_pandas.tseries = types.ModuleType('pandas.tseries')
    fake_pandas.tseries.api = types.ModuleType('pandas.tseries.api')
    fake_pandas.tseries.api.indexed_frame = lambda: FakeDataFrame
    fake_pandas.api = types.ModuleType('pandas.api')
    fake_pandas.api.extensions = types.ModuleType('pandas.api.extensions')
    fake_pandas.api.types = types.ModuleType('pandas.api.types')
    fake_pandas.api.indexers = types.ModuleType('pandas.api.indexers')
    fake_pandas.compat = types.ModuleType('pandas.compat')
    fake_pandas.compat.numpy_function = lambda *a, **kw: (lambda f: f): None
    fake_pandas.concat = lambda *a, **kw: FakeDataFrame()
    fake_pandas.merge = lambda *a, **kw: FakeDataFrame()
    fake_pandas.to_datetime = lambda *a, **kw: None
    fake_pandas.isna = lambda *a, **kw: FakeDataFrame()
    fake_pandas.notna = lambda *a, **kw: FakeDataFrame()
    fake_pandas.DataFrame.__class__ = FakeDataFrame

    sys.modules['pandas'] = fake_pandas
    sys.modules['pandas.core'] = fake_pandas.core
    sys.modules['pandas.core.frame'] = fake_pandas.core.frame
    sys.modules['pandas.core.series'] = fake_pandas.core.series
    sys.modules['pandas.errors'] = fake_pandas.errors
    sys.modules['pandas._testing'] = fake_pandas._testing
    sys.modules['pandas.io'] = fake_pandas.io
    sys.modules['pandas.io.formats'] = fake_pandas.io.formats
    sys.modules['pandas.io.formats.style'] = fake_pandas.io.formats.style
    sys.modules['pandas.plotting'] = fake_pandas.plotting
    sys.modules['pandas.tseries'] = fake_pandas.tseries
    sys.modules['pandas.tseries.api'] = fake_pandas.tseries.api
    sys.modules['pandas.api'] = fake_pandas.api
    sys.modules['pandas.api.extensions'] = fake_pandas.api.extensions
    sys.modules['pandas.api.types'] = fake_pandas.api.types
    sys.modules['pandas.api.indexers'] = fake_pandas.api.indexers
    sys.modules['pandas.compat'] = fake_pandas.compat

    # 构造轻量级 paddlex（只需要 paddleocr 用到的部分）
    fake_paddlex = types.ModuleType('paddlex')
    fake_paddlex.__version__ = '3.5.0'

    fake_paddlex.cv = types.ModuleType('paddlex.cv')
    fake_paddlex.cv.datasets = types.ModuleType('paddlex.cv.datasets')
    fake_paddlex.cv.datasets.transforms = types.ModuleType('paddlex.cv.datasets.transforms')

    fake_paddlex.utils = types.ModuleType('paddlex.utils')
    fake_paddlex.utils.logging = types.ModuleType('paddlex.utils.logging')

    fake_paddlex.utils.logging.get_logger = lambda *a, **kw: types.ModuleType('logger')
    fake_paddlex.utils.env_info = lambda *a, **kw: {}

    fake_paddlex.transforms = types.ModuleType('paddlex.transforms')
    fake_paddlex.transforms.Compose = lambda *a, **kw: None
    fake_paddlex.transforms.Resize = lambda *a, **kw: None

    fake_paddlex.download = lambda *a, **kw: None

    sys.modules['paddlex'] = fake_paddlex
    sys.modules['paddlex.cv'] = fake_paddlex.cv
    sys.modules['paddlex.cv.datasets'] = fake_paddlex.cv.datasets
    sys.modules['paddlex.cv.datasets.transforms'] = fake_paddlex.cv.datasets.transforms
    sys.modules['paddlex.utils'] = fake_paddlex.utils
    sys.modules['paddlex.utils.logging'] = fake_paddlex.utils.logging
    sys.modules['paddlex.utils.env_info'] = fake_paddlex.utils.env_info
    sys.modules['paddlex.transforms'] = fake_paddlex.transforms
    sys.modules['paddlex.download'] = fake_paddlex.download


_patch_paddlex()
