import asyncio
import inspect


def pytest_configure(config):
    config.addinivalue_line('markers', 'asyncio: run async test functions with asyncio')


def pytest_pyfunc_call(pyfuncitem):
    if 'asyncio' not in pyfuncitem.keywords:
        return None
    testfunction = pyfuncitem.obj
    if not inspect.iscoroutinefunction(testfunction):
        return None
    fixture_names = pyfuncitem._fixtureinfo.argnames
    testargs = {name: pyfuncitem.funcargs[name] for name in fixture_names}
    asyncio.run(testfunction(**testargs))
    return True
