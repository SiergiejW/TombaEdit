"""Selection lines printed to the console.

Every line says what was selected and ends with what is open: the resource,
its load table and group, and the area and section those are. A line then
stands on its own when it is copied somewhere else.
"""
context = ''


def announce(text):
    print(f'selected: {text}' + (f' | in {context}' if context else ''))
