import contextlib
from .files import Files

def source_allowed(ctx,share,path):
    return not (isinstance(share,str) and share.startswith('pool:') and hasattr(ctx,'shared_usb_path')) or ctx.shared_usb_path(share[5:],path)

@contextlib.contextmanager
def source_directory(ctx,share,path=''):
    if not source_allowed(ctx,share,path):raise ValueError('This is private personal storage; choose a public USB folder or your own library')
    if isinstance(share,str) and share.startswith('pool:'):
        from .external import External
        view=External(ctx).file_view({'pool':share[5:]},registered_pool=True)
    elif isinstance(share,str) and share.startswith('foreign:'):
        from .external import External
        from .foreign import Foreign
        base=getattr(ctx,'base',ctx);view=Foreign(base,External(base)).file_view(share[8:])
    else:view=Files(ctx)
    with view.directory(share,path) as value:yield value
