# Testing

Because classes take their dependencies through constructors, most unit tests need no container at
all: build the object with fakes and test it. Reach for the container when a test should exercise
the real wiring with a few pieces replaced.

## Clone, then override

```python
test = container.clone()
test.override(interface=PaymentGateway, implementation=FakePaymentGateway)
test.validate()
```

A clone has the same providers as the original and nothing else in common with it:

| Carried over to the clone           | Not carried over                          |
|-------------------------------------|-------------------------------------------|
| All providers and hooks             | Singletons that were already built        |
| Objects handed over with `bind`     | The container's own `lifespan`            |

Overrides on a clone never reach the original, so a test cannot leak into the next one.

## What an override does

| You pass   | The replacement                                                                  |
|------------|----------------------------------------------------------------------------------|
| A class    | Is built by dixy from its own constructor, with the lifetime of the original     |
| An object  | Is used as it is. The container neither builds nor closes it                     |

For an alias the lifetime of the original is that of its source. For an `instance` it is the
container's: the replacement is built once and replaces the object you bound.

A replacement class starts clean: the original provider's keyword arguments, factory, setup,
teardown and lifespan do not apply to it. Give a fake constructor defaults for the plain values it
needs, or pass a ready object.

Three things to keep in mind:

- Override before the dependency is first used. A singleton that already exists stays in place.
- Overriding an [alias](providers.md#sharing-one-instance-under-two-interfaces) replaces that
  interface only: whoever asks for its source still gets the real one. Override the source to
  replace both.
- Validate after overriding. A fake with different dependencies changes the wiring, and validation
  tells you so immediately.

## Functions with `@inject`

A function decorated with a [container accessor](inject.md#a-container-that-comes-later) follows
whatever container is active, so a test activates a clone. For a single call, passing a fake by
name is enough: an argument the caller passes always wins over injection.

[`testing_overrides.py`](../examples/testing_overrides.py) shows a clone with a class override and
an object override.
