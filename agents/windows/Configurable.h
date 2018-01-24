#ifndef Configurable_h
#define Configurable_h

#include <sstream>
#include <string>
#include "Configuration.h"
#include "SettingsCollector.h"
#include "stringutil.h"
#include "types.h"

class WinApiAdaptor;

class ConfigurableBase {
public:
    explicit ConfigurableBase(const WinApiAdaptor &winapi) : _winapi(winapi) {}
    virtual ~ConfigurableBase() = default;
    ConfigurableBase(const ConfigurableBase &) = delete;
    ConfigurableBase &operator=(const ConfigurableBase &) = delete;

    virtual void feed(const std::string &key, const std::string &value) = 0;
    virtual void output(const std::string &key, std::ostream &out) const = 0;
    virtual void startFile() = 0;
    virtual void startBlock() = 0;

protected:
    const WinApiAdaptor &_winapi;
};

template <typename ValueT>
class Configurable : public ConfigurableBase {
public:
    Configurable(Configuration &config, const char *section, const char *key,
                 const ValueT &def, const WinApiAdaptor &winapi)
        : ConfigurableBase(winapi), _value(def) {
        config.reg(section, key, this);
    }

    virtual ~Configurable() = default;

    ValueT *operator->() { return &_value; }

    const ValueT *operator->() const { return &_value; }

    ValueT &operator*() { return _value; }

    const ValueT &operator*() const { return _value; }

    virtual void startFile() override {}
    virtual void startBlock() override {}

    virtual void feed(const std::string &, const std::string &value) override {
        startBlock();
        _value = from_string<ValueT>(_winapi, value);
    }

    virtual void output(const std::string &key,
                        std::ostream &out) const override {
        out << key << " = " << _value << "\n";
    }

private:
    ValueT _value;
};

/**
 * regular list collector which allows multiple assignments to the same
 * variable. The addmode and block mode decide how these multiple assignments
 * are combined
 **/
template <typename ContainerT, typename BlockModeT = BlockMode::Nop<ContainerT>,
          typename AddModeT = AddMode::Append<ContainerT>>
class ListConfigurable : public ConfigurableBase {
    typedef typename ContainerT::value_type DataT;

public:
    ListConfigurable(Configuration &config, const char *section,
                     const char *key, const WinApiAdaptor &winapi)
        : ConfigurableBase(winapi) {
        config.reg(section, key, this);
    }

    virtual ~ListConfigurable() = default;

    ContainerT *operator->() { return &_values; }

    const ContainerT *operator->() const { return &_values; }

    ContainerT &operator*() { return _values; }

    const ContainerT &operator*() const { return _values; }

    virtual void startFile() {
        _add_mode.startFile(_values);
        _block_mode.startFile(_values);
    }

    virtual void startBlock() { _block_mode.startBlock(_values); }

    virtual void feed(const std::string &, const std::string &value) override {
        try {
            this->add(from_string<DataT>(_winapi, value));
        } catch (const StringConversionError &e) {
            std::cerr << e.what() << std::endl;
        }
    }

    virtual void output(const std::string &key,
                        std::ostream &out) const override {
        for (const DataT &data : _values) {
            out << key << " = " << data << "\n";
        }
    }

    /**
     * returns whether there ever was an assignment to this configurable
     **/
    bool wasAssigned() const { return _was_assigned; }

    virtual void clear() { _values.clear(); }

    // only valid with a grouping adder. it's important to understand that
    // due to how templates in C++ work, these functions are not compiled
    // for template-instantiations where they aren't used so even though
    // they wouldn't compile with non-grouping adders, this is not a
    // problem. (google SFINAE)
    void setGroupFunction(
        typename AddMode::PriorityAppendGrouped<ContainerT>::GroupFunction
            function) {
        _add_mode.setGroupFunction(function);
    }

    bool feedInner(const std::string &key, const std::string &value) {
        return _add_mode.addGroup(_values, key.c_str(), value.c_str());
    }

    void add(const DataT &data) {
        _add_mode.add(_values, data);
        _was_assigned = true;
    }

protected:
    ContainerT &values() { return _values; }

    const ContainerT &values() const { return _values; }

private:
    ContainerT _values;
    BlockModeT _block_mode;
    AddModeT _add_mode;

    bool _was_assigned{false};
};

template <typename DataT>
class KeyedListConfigurable : public ConfigurableBase {
    typedef std::vector<std::pair<std::string, DataT>> ContainerT;

public:
    KeyedListConfigurable(Configuration &config, const char *section,
                          const char *key, const WinApiAdaptor &winapi)
        : ConfigurableBase(winapi) {
        config.reg(section, key, this);
    }

    virtual ~KeyedListConfigurable() = default;

    virtual void feed(const std::string &var,
                      const std::string &value) override {
        size_t pos = var.find_first_of(" ");
        std::string key;
        if (pos != std::string::npos) {
            key = std::string(var.begin() + pos + 1, var.end());
        }
        startBlock();
        try {
            _add_mode.add(_values, std::make_pair(key, from_string<DataT>(
                                                           _winapi, value)));
        } catch (const StringConversionError &e) {
            std::cerr << e.what() << std::endl;
        }
    }

    virtual void output(const std::string &key,
                        std::ostream &out) const override {
        for (const std::pair<std::string, DataT> &data : this->values()) {
            out << key << " " << data.first << " = " << data.second << "\n";
        }
    }

    ContainerT *operator->() { return &_values; }

    const ContainerT *operator->() const { return &_values; }

    ContainerT &operator*() { return _values; }

    const ContainerT &operator*() const { return _values; }

    virtual void startFile() override { _add_mode.startFile(_values); }
    virtual void startBlock() override {}

    void clear() { _values.clear(); }

    void add(const DataT &data) { _add_mode.add(_values, data); }

protected:
    ContainerT &values() { return _values; }

    const ContainerT &values() const { return _values; }

private:
    ContainerT _values;
    AddMode::PriorityAppend<ContainerT> _add_mode;
};

/**
 * Splitting list configurable produces a list of items but expects all
 * elements in a single assignment, separated by a separator
 **/
template <typename ContainerT, typename BlockModeT = BlockMode::Nop<ContainerT>,
          typename AddModeT = AddMode::Append<ContainerT>>
class SplittingListConfigurable
    : public ListConfigurable<ContainerT, BlockModeT, AddModeT> {
    typedef ListConfigurable<ContainerT, BlockModeT, AddModeT> SuperT;
    typedef typename ContainerT::value_type DataT;
    typedef std::function<std::string(const std::string &)> MapFunction;

public:
    SplittingListConfigurable(Configuration &config, const char *section,
                              const char *key, const WinApiAdaptor &winapi,
                              const MapFunction &mapFunction =
                                  [](const std::string &s) { return s; },
                              char split_char = ' ')
        : SuperT(config, section, key, winapi)
        , _mapFunction(mapFunction)
        , _split_char(split_char) {}

    virtual ~SplittingListConfigurable() = default;

    virtual void feed(const std::string &key,
                      const std::string &value) override {
        SuperT::clear();
        std::stringstream str(value);
        std::string item;
        while (getline(str, item, _split_char)) {
            SuperT::feed(key, _mapFunction(item));
        }
    }

    virtual void output(const std::string &key,
                        std::ostream &out) const override {
        out << key << " =";
        for (const DataT &data : this->values()) {
            out << " " << data;
        }
        out << "\n";
    }

private:
    const MapFunction _mapFunction;
    char _split_char;
};

#endif  // Configurable_h
