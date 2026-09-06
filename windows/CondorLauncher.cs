using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Condor.Windows
{
    internal static class CondorLauncher
    {
        private const string AppId = "ARTX.Condor.Local";

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

        [STAThread]
        private static int Main()
        {
            try
            {
                SetCurrentProcessExplicitAppUserModelID(AppId);
                string root = AppDomain.CurrentDomain.BaseDirectory;
                string pythonw = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
                string entry = Path.Combine(root, "condor_app.pyw");

                if (!File.Exists(pythonw) || !File.Exists(entry))
                {
                    MessageBox.Show(
                        "Execute scripts\\install.ps1 antes de abrir o Condor.",
                        "Condor AI",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return 1;
                }

                Process.Start(new ProcessStartInfo
                {
                    FileName = pythonw,
                    Arguments = "\"" + entry + "\"",
                    WorkingDirectory = root,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                });
                return 0;
            }
            catch (Exception error)
            {
                MessageBox.Show(
                    "O Condor não conseguiu iniciar.\n\n" + error.Message,
                    "Condor AI",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return 1;
            }
        }
    }
}
