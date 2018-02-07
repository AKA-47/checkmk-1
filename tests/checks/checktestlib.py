import types

class Tuploid(object):
    """Base class for values with (potentially variadic) tuple representations"""

    def __eq__(self, other_value):
        if isinstance(other_value, self.__class__):
            return other_value.tuple == self.tuple
        elif type(other_value) == tuple:
            return all(x==y for x, y in zip(other_value, self.tuple))

    def __ne__(self, other_value):
        return not self.__eq__(other_value)

    @property
    def tuple(self):
        raise NotImplementedError()

    def __iter__(self):
        for x in self.tuple:
            yield x


class PerfValue(Tuploid):
    """Represents a single perf value"""

    def __init__(self, key, value, warn=None, crit=None, minimum=None, maximum=None):
        # TODO: This is very basic. There is more way more magic involved
        #       in what kind of values are allowed as metric names.
        #       I'm not too sure unicode should be allowed, either.
        assert type(key) in [str, unicode]
        assert " " not in key   # This leads to serious errors
        assert "=" not in key   # The parsing around this is way too funky and doesn't work properly
        assert "\n" not in key
        self.key = key

        # NOTE: The CMC as well as all other Nagios-compatible cores do accept a
        #       string value that may contain a unit, which is in turn available
        #       for use in PNP4Nagios templates. Check_MK defines its own semantic
        #       context for performance values using Check_MK metrics. It is therefore
        #       preferred to return a "naked" scalar.
        assert type(value) in [int, float]
        self.value = value

        assert type(warn) in [int, float, types.NoneType]
        self.warn = warn
        assert type(crit) in [int, float, types.NoneType]
        self.crit = crit
        assert type(minimum) in [int, float, types.NoneType]
        self.minimum = minimum
        assert type(maximum) in [int, float, types.NoneType]
        self.maximum = maximum

    @property
    def tuple(self):
        return (self.key, self.value, self.warn, self.crit, self.minimum, self.maximum)

    def __repr__(self):
        return "PerfValue(%s, %s, %s, %s, %s, %s)" % (self.key, self.value, self.warn,
                                                      self.crit, self.minimum, self.maximum)


class BasicCheckResult(Tuploid):
    """
    A basic check result

    This class models a basic check result (status, infotext, perfdata) and provides
    facilities to match it against conditions, such as 'Status is...' or
    'Infotext contains...'
    """

    def __init__(self, status, infotext, perfdata=None):
        """We perform some basic consistency checks during initialization"""

        assert status in [0, 1, 2, 3]
        assert type(infotext) == str
        assert "\n" not in infotext
        self.status = status
        self.infotext = infotext
        if perfdata is not None:
            assert type(perfdata) == list

            self.perfdata = []
            for entry in perfdata:
                assert type(entry) in [tuple, PerfValue]
                if type(entry) is tuple:
                    self.perfdata.append(PerfValue(*entry))
                else:
                    self.perfdata.append(entry)
        else:
            self.perfdata = None

    @property
    def tuple(self):
        return (self.status, self.infotext, self.perfdata)

    def __repr__(self):
        return 'BasicCheckResult(%s, "%s", %s)' % (self.status, self.infotext, self.perfdata)


class CheckResult(object):
    """
    A check result potentially consisting of multiple subresults,
    as returned by yield-style checks

    Initializing test results using this has the following advantages:
    -Some basic consistency checks are being performed, making sure the
     check's result conforms to the API
    -A common interface to test assertions is provided, regardless of whether
     or not the check uses subresults via the yield-API
    -The check's code is being run, and doesn't disappear in the yield-APIs
     generator-induced laziness.
    """

    def __init__(self, result):
        """
        Initializes a list of subresults using BasicCheckResult.

        If the result is already a plain check result in its tuple representation,
        we initialize a list of length 1.
        """

        if type(result) == types.GeneratorType:
            self.subresults = []
            for subresult in result:
                self.subresults.append(BasicCheckResult(*subresult))
        else:
            self.subresults = [ BasicCheckResult(*result) ]

    @property
    def perfdata(self):
        perfdata = []
        for subresult in self.subresults:
            perfdata += subresult.perfdata if subresult.perfdata else []
        return perfdata


class DiscoveryEntry(Tuploid):
    """A single entry as returned by the discovery (or in oldspeak: inventory) function."""

    def __init__(self, entry):
        item, default_params = entry
        assert type(item) in [ str, unicode, types.NoneType ]
        self.item = item
        self.default_params = default_params

    @property
    def tuple(self):
        return (self.item, self.default_params)


class DiscoveryResult(object):
    """
    The result of the discovery as a whole.

    Much like in the case of the check result, this also makes sure
    that yield-based discovery functions run, and that no exceptions
    get lost in the laziness.
    """

    # TODO: Add some more consistency checks here.
    def __init__(self, result):
        self.entries = []
        for entry in result:
            self.entries.append(DiscoveryEntry(entry))

    def __eq__(self, other_value):
        return all(entry in other_value for entry in self.entries) and \
               all(other_entry in self.entries for other_entry in other_value)
