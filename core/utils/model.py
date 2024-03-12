
def model_import_by_name(module_from, module_name):
    """ Import a named object from a module in the context of this function.
    """
    try:
        module = __import__(module_from, globals(), locals(), [module_name])
    except ImportError:
        return None
    return vars(module)[module_name]
