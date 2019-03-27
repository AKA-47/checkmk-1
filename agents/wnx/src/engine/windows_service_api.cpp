
// provides basic api to start and stop service
#include <stdafx.h>

#include <shlobj_core.h>

#include <chrono>
#include <cstdint>   // wchar_t when compiler options set weird
#include <iostream>  // test commands
#include "common/wtools.h"

#include "tools/_kbd.h"
#include "tools/_process.h"

#include "service_processor.h"    // cmk service implementation class
#include "windows_service_api.h"  // windows api abstracted

#include "external_port.h"  // windows api abstracted

#include "cap.h"
#include "cfg.h"
#include "cvt.h"
#include "upgrade.h"

// out of namespace
bool G_SkypeTesting = false;

namespace cma {

namespace srv {
// on -install
// Doesn't create artifacts in program. Changes registry.
int InstallMainService() {
    auto result = wtools::InstallService(
        cma::srv::kServiceName,         // Name of service
        cma::srv::kServiceDisplayName,  // Name to display
        cma::srv::kServiceStartType,    // Service start type
        nullptr,  // cma::srv::kServiceDependencies,  // Dependencies
        nullptr,  // cma::srv::kServiceAccount,       // Service running account
        nullptr   // cma::srv::kServicePassword       // Password of the account
    );
    return result ? 0 : 1;
}

// on -remove
// Doesn't create artifacts in program. Changes registry.
int RemoveMainService() {
    auto result = wtools::UninstallService(cma::srv::kServiceName);
    return result ? 0 : 1;
}

// #POC: to be deleted
static bool execMsi() {
    wchar_t* str = nullptr;
    if (SHGetKnownFolderPath(FOLDERID_System, KF_FLAG_DEFAULT, NULL, &str) !=
        S_OK)
        return false;
    std::wstring exe = str;
    exe += L"\\msiexec.exe";
    std::string command;
    command.assign(exe.begin(), exe.end());
    std::wstring options =
        L" /i \"C:\\z\\m\\check_mk\\agents\\wnx\\build\\install\\Release\\check_mk_service.msi\" "
        L"REINSTALL=ALL REINSTALLMODE=amus "
        L" /quiet";

    // start process
    STARTUPINFO si;
    PROCESS_INFORMATION pi;

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcess(nullptr,                          // application name
                       (LPWSTR)(exe + options).c_str(),  // Command line options
                       NULL,   // Process handle not inheritable
                       NULL,   // Thread handle not inheritable
                       FALSE,  // Set handle inheritance to FALSE
                       0,      // No creation flags
                       NULL,   // Use parent's environment block
                       NULL,   // Use parent's starting directory
                       &si,    // Pointer to STARTUPINFO structure
                       &pi))   // Pointer to PROCESS_INFORMATION structure
    {
        return false;
    }

    return true;
}

// #POC This is part of poc, testing command which finds an update file and
// execute it
static void CheckForCommand(std::string& Command) {
    Command = "";
    char dir[MAX_PATH * 2] = "";
    GetCurrentDirectoryA(MAX_PATH * 2, dir);
    std::cout << dir << ": tick\n";
    try {
        constexpr const char* kUpdateFileCommandDone = "update.command.done";
        std::string done_file_name = kUpdateFileCommandDone;
        std::ifstream done_file(done_file_name.c_str(), std::ios::binary);

        if (done_file.good()) {
            // first stage - deleting file
            done_file.close();
            auto ret = ::DeleteFileA(done_file_name.c_str());
            if (!ret) {
                xlog::l("Cannot Delete File %s with error %d",
                        done_file_name.c_str(), GetLastError());
                return;
            }
        }
        constexpr const char* kUpdateFileCommand = "update.command";
        std::string command_file_name = kUpdateFileCommand;
        std::ifstream command_file(command_file_name.c_str(), std::ios::binary);

        if (!command_file.good()) return;  // nothing todo

        // now is more interesting event
        xlog::l("File %s found, try to exec command", command_file_name.c_str())
            .print();

        command_file.seekg(0, std::ios::end);
        int length = static_cast<int>(command_file.tellg());
        command_file.seekg(0, std::ios::beg);
        if (length > MAX_PATH) {
            // sanity check - too long file will be ignored
            xlog::l("File %s is too big", command_file_name.c_str()).print();
            command_file.close();
        } else {
            // store command & rename file
            char buffer[MAX_PATH * 2];
            command_file.read(buffer, length);
            buffer[length] = 0;
            command_file.close();
            auto ret =
                ::MoveFileA(command_file_name.c_str(), done_file_name.c_str());
            if (ret) {
                Command = buffer;
                xlog::l("To exec %s", Command.c_str());
                execMsi();
            } else {
                xlog::l("Cannot Rename File from to %s %s with error %d",
                        done_file_name.c_str(), GetLastError());
            }
        }
    } catch (...) {
    }
    return;
}

// on -test self
int TestMainServiceSelf(int Interval) {
    XLOG::setup::DuplicateOnStdio(true);
    XLOG::setup::ColoredOutputOnStdio(true);
    bool stop = false;

    if (Interval < 0) Interval = 0;
    // not a best method to call thread, but this is only for VISUAL testing
    std::thread kick_and_print([&stop, Interval]() {
        auto port = cma::cfg::groups::global.port();

        using namespace asio;

        io_context ios;
        std::string address = "127.0.0.1";

        ip::tcp::endpoint endpoint(ip::make_address(address), port);

        asio::ip::tcp::socket socket(ios);
        std::error_code ec;

        while (!stop) {
            auto enc = cma::cfg::groups::global.globalEncrypt();
            auto password = enc ? cma::cfg::groups::global.password() : "";
            socket.connect(endpoint, ec);
            if (ec.value() != 0) {
                XLOG::l("Can't connect to {}:{}, waiting for 5 seconds",
                        address, port);

                // methods below is not a good still we do not want
                // to over complicate the code just for testing purposes
                for (int i = 0; i < 5; i++) {
                    if (stop) break;
                    cma::tools::sleep(1000);
                }
                if (stop) break;
                continue;
            }
            error_code error;
            std::vector<char> v;
            for (;;) {
                char text[4096];
                auto count = socket.read_some(asio::buffer(text), error);
                if (error.value()) break;
                if (count) {
                    v.insert(v.end(), text, text + count);
                }
            }
            XLOG::l.i("Received {} bytes", v.size());
            if (enc && password[0]) {
                XLOG::l.i("Decrypting {} bytes", v.size());
                // attempt to decode
                cma::encrypt::Commander e(password);
                auto size = v.size();
                v.resize(size + 1024);
                auto [ret, sz] = e.decode(v.data(), size, true);
                XLOG::l.i("Decrypted {} bytes {}", ret, sz);
            }
            socket.close();

            // methods below is not a good still we do not want
            // to over complicate the code just for testing purposes
            for (int i = 0; i < Interval; i++) {
                if (stop) break;
                cma::tools::sleep(1000);
            }
            if (Interval == 0) break;
        }
        XLOG::l.i("Leaving testing thread");
    });

    ExecMainService();  // blocking call waiting for keypress
    stop = true;
    if (kick_and_print.joinable()) {
        XLOG::l.i("Waiting for testing thread");
        kick_and_print.join();
        XLOG::l.i("!");
    }

    return 0;
}

// on -test
int TestMainService(const std::wstring& What, int Interval) {
    using namespace std::chrono;
    if (What == L"port") {
        // simple test for ExternalPort. will be disabled in production.
        try {
            cma::world::ExternalPort port(nullptr);
            port.startIo([](const std::string Ip) -> std::vector<uint8_t> {
                return std::vector<uint8_t>();
            });  //
            std::this_thread::sleep_until(steady_clock::now() + 10000ms);
            port.shutdownIo();  //

        } catch (const std::exception& e) {
            xlog::l("Exception is not allowed here %s", e.what());
        }
    } else if (What == L"mt") {
        // test for main thread. will be disabled in production
        // to find file, read and start update POC.
        try {
            using namespace std::chrono;
            std::string command = "";
            cma::srv::ServiceProcessor sp(2000ms, [&command](const void* Sp) {
                CheckForCommand(command);
                if (command[0]) {
                    cma::tools::RunDetachedCommand(command);
                    command = "";
                }
                return true;
            });
            sp.startTestingMainThread();
            std::cout << "Press any key to stop testing";
            cma::tools::GetKeyPress();
            sp.stopTestingMainThread();

        } catch (const std::exception& e) {
            xlog::l("Exception is not allowed here %s", e.what());
        }
    } else if (What == L"legacy") {
        using namespace std::chrono;
        std::string command = "";
        cma::srv::ServiceProcessor sp(
            2000ms, [&command](const void* Sp) { return true; });
        sp.startServiceAsLegacyTest();
        sp.stopService();
    } else if (What == L"self") {
        TestMainServiceSelf(Interval);
    } else {
        XLOG::setup::DuplicateOnStdio(true);
        XLOG::setup::ColoredOutputOnStdio(true);
        XLOG::l(
            "Unsupported second parameter\n\tAllowed: port, mt, legacy, self");
    }

    return 0;
}  // namespace srv

// on -cvt
// may be used as internal API function to convert ini to yaml
// GTESTED internally
int ExecCvtIniYaml(std::filesystem::path IniFile,
                   std::filesystem::path YamlFile, bool DiagnosticMessage) {
    //
    auto flag = DiagnosticMessage ? XLOG::kStdio : 0;
    namespace fs = std::filesystem;
    fs::path file = IniFile;
    std::error_code ec;
    if (!fs::exists(file, ec)) {
        XLOG::l(flag)("File not found '{}'", IniFile.u8string());
        return 3;
    }
    cma::cfg::cvt::Parser parser_converter;
    parser_converter.prepare();
    if (!parser_converter.readIni(file, false)) {
        XLOG::l(flag)("Failed Load '{}'", fs::absolute(IniFile).u8string());
        return 2;
    }
    auto yaml = parser_converter.emitYaml();

    try {
        if (YamlFile.empty()) {
            std::cout << yaml;
        } else {
            auto file = YamlFile;
            std::ofstream ofs(file.u8string());
            ofs << yaml;
            ofs.close();
            XLOG::l.i(flag, "Successfully Converted {} -> {}",
                      fs::absolute(IniFile).u8string(),
                      fs::absolute(YamlFile).u8string());
        }
    } catch (const std::exception& e) {
        XLOG::l(flag) << "Exception: '" << e.what() << "' in ExecCvtIniYaml"
                      << std::endl;
        return 1;
    }

    return 0;
}

std::vector<std::wstring> SupportedSections{
    wtools::ConvertToUTF16(cma::section::kDfName)};

// on -section
// NOT GTESTED
int ExecSection(const std::wstring& SecName, int RepeatPause,
                bool DianosticMessages) {
    //
    XLOG::setup::ColoredOutputOnStdio(true);
    if (DianosticMessages) {
        XLOG::setup::DuplicateOnStdio(true);
        XLOG::setup::EnableDebugLog(true);
        XLOG::setup::EnableTraceLog(true);
    }

    while (1) {
        if (SecName == wtools::ConvertToUTF16(cma::section::kDfName)) {
            provider::Df df;
            auto x = df.generateContent(cma::section::kUseEmbeddedName, true);
            XLOG::stdio("{}", x);
        } else {
            XLOG::l("Section {} not supported", wtools::ConvertToUTF8(SecName));
            break;
        }

        if (RepeatPause <= 0) break;
        cma::tools::sleep(RepeatPause * 1000);
    }

    return 0;
}

// on -exec
// we run entry point as normal process
// this is testing routine probably eliminated from the production build
// THIS ROUTINE DOESN'T USE wtools::ServiceController and Windows Service API
// Just internal to debug logic
int ExecMainService(bool DuplicateOn) {
    using namespace cma::srv;
    using namespace std::chrono;

    milliseconds Delay = 1000ms;
    auto processor = new ServiceProcessor(Delay, [](const void* Processor) {
        // default embedded callback for exec
        // atm does nothing
        return true;
    });

    processor->startService();

    try {
        std::string cmd;
        if (DuplicateOn) XLOG::setup::DuplicateOnStdio(true);
        XLOG::setup::ColoredOutputOnStdio(true);
        XLOG::l.i("Press any key to stop");
        auto ret = cma::tools::GetKeyPress();
    } catch (const std::exception& e) {
        xlog::l("Exception \"%s\"", e.what());
    }
    XLOG::l.i("Server is stopping");
    processor->stopService();
    if (DuplicateOn) XLOG::setup::DuplicateOnStdio(false);

    return 0;
}

// on -cap
int ExecCap() {
    XLOG::setup::DuplicateOnStdio(true);
    XLOG::setup::ColoredOutputOnStdio(true);
    XLOG::setup::EnableDebugLog(true);
    XLOG::setup::EnableTraceLog(true);
    XLOG::l.i("Installing...");
    cma::cfg::cap::Install();
    XLOG::l.i("End of!");
    return 0;
}

// on -start_legacy
int ExecStartLegacy() {
    using namespace cma::cfg::upgrade;

    XLOG::setup::DuplicateOnStdio(true);
    XLOG::setup::ColoredOutputOnStdio(true);
    XLOG::setup::EnableDebugLog(true);
    XLOG::setup::EnableTraceLog(true);
    FindActivateStartLegacyAgent();
    XLOG::l.i("End of!");

    return 0;
}

// on -stop_legacy
int ExecStopLegacy() {
    using namespace cma::cfg::upgrade;

    XLOG::setup::DuplicateOnStdio(true);
    XLOG::setup::ColoredOutputOnStdio(true);
    XLOG::setup::EnableDebugLog(true);
    XLOG::setup::EnableTraceLog(true);
    FindStopDeactivateLegacyAgent();
    XLOG::l.i("End of!");

    return 0;
}

// on -upgrade
int ExecUpgradeParam(bool Force) {
    using namespace cma::cfg::upgrade;

    XLOG::setup::DuplicateOnStdio(true);
    XLOG::setup::ColoredOutputOnStdio(true);
    XLOG::setup::EnableDebugLog(true);
    XLOG::setup::EnableTraceLog(true);
    UpgradeLegacy(Force);
    XLOG::l.i("End of!");

    return 0;
}

// simple scanner of multi_sz strings
// #TODO gtest?
const wchar_t* GetMultiSzEntry(wchar_t*& Pos, const wchar_t* End) {
    auto sz = Pos;
    if (sz >= End) return nullptr;

    auto len = wcslen(sz);
    if (len == 0) return nullptr;  // last string in multi_sz

    Pos += len + 1;
    return sz;
}

// on -skype
// verify that skype business is present
int ExecSkypeTest() {
    G_SkypeTesting = true;
    XLOG::setup::DuplicateOnStdio(true);
    XLOG::setup::ColoredOutputOnStdio(true);
    ON_OUT_OF_SCOPE(XLOG::setup::DuplicateOnStdio(false););
    XLOG::l.i("<<<Skype testing>>>");
    cma::provider::SkypeProvider skype;
    auto result = skype.generateContent(cma::section::kUseEmbeddedName, true);
    XLOG::l.i("*******************************************************");
    if (result.size())
        XLOG::l.i("{}", result);
    else {
        auto counter_str = wtools::perf::ReadPerfCounterKeyFromRegistry(false);
        auto data = counter_str.data();
        const auto end = counter_str.data() + counter_str.size();
        for (;;) {
            // get id
            auto potential_id = GetMultiSzEntry(data, end);
            if (!potential_id) break;

            // get name
            auto potential_name = GetMultiSzEntry(data, end);
            if (!potential_name) break;

            // check name
            result += wtools::ConvertToUTF8(potential_id) + ": " +
                      wtools::ConvertToUTF8(potential_name) + "\n";
        }
        XLOG::l.i("{}", result);
    }
    XLOG::l.i("*******************************************************");
    XLOG::l.i("Using Usual Registry Keys:");

    auto skype_counters = cma::provider::internal::GetSkypeCountersVector();
    skype_counters->clear();
    skype_counters->push_back(L"Memory");
    skype_counters->push_back(L"510");
    result = skype.generateContent(cma::section::kUseEmbeddedName, true);

    XLOG::l.i("*******************************************************");
    XLOG::l.i("{}", result);
    XLOG::l.i("*******************************************************");
    //    skype.generateContent();
    XLOG::l.i("<<<Skype testing END>>>");
    return 0;
}

// normal BLOCKING FOR EVER CALL
// blocking call from the Windows Service Manager
// exception free
// returns -1 on failure
int ServiceAsService(
    std::chrono::milliseconds Delay,
    std::function<bool(const void* Processor)> InternalCallback) noexcept {
    using namespace cma::srv;

    // infinite loop to protect from exception
    while (1) {
        try {
            auto processor = new ServiceProcessor(Delay, InternalCallback);
            wtools::ServiceController service_controller(processor);
            auto ret = service_controller.registerAndRun(
                cma::srv::kServiceName);  // we will stay here till
                                          // service will be stopped
                                          // itself or from outside
            return ret ? 0 : -1;
        } catch (const std::exception& e) {
            XLOG::l.crit("Exception hit {} in main proc", e.what());
        } catch (...) {
            XLOG::l.crit("Unknown Exception in main proc");
        }
    }
    // unreachable
}

}  // namespace srv
};  // namespace cma
