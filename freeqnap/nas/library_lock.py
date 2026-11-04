import functools

def serialized(method):
    @functools.wraps(method)
    def call(self,*args,**kwargs):
        with self.storage_lock:return method(self,*args,**kwargs)
    return call
