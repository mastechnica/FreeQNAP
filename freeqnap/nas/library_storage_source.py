import contextlib
from .files import Files

@contextlib.contextmanager
def source_directory(ctx,share,path=''):
    if isinstance(share,str) and share.startswith('pool:'):
        from .external import External
        view=External(ctx).file_view({'pool':share[5:]},registered_pool=True)
    elif isinstance(share,str) and share.startswith('foreign:'):
        from .external import External
        from .foreign import Foreign
        view=Foreign(ctx,External(ctx)).file_view(share[8:])
    else:view=Files(ctx)
    with view.directory(share,path) as value:yield value
