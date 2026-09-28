using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Condor.Windows
{
    internal static class CondorLauncher
    {
        private const string AppId = "ARTX.Condor.Local";
        private const string UiUrl = "http://127.0.0.1:7777/ui/index.html";

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
                        "O CONDOR precisa ser reparado.\n\nAbra o CondorSetup.exe e instale de novo na mesma pasta " +
                        "(sua memória e seus modelos são preservados).",
                        "CONDOR", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return 1;
                }

                bool jaRodando = NucleoPronto(400);
                Process.Start(new ProcessStartInfo
                {
                    FileName = pythonw,
                    Arguments = "\"" + entry + "\"",
                    WorkingDirectory = root,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                });
                if (jaRodando) return 0;

                // Primeira abertura: o núcleo e o modelo local levam alguns
                // segundos. A tela de carregamento some sozinha quando a
                // janela do CONDOR estiver pronta.
                Application.EnableVisualStyles();
                using (var splash = new Carregando(root))
                    Application.Run(splash);
                return 0;
            }
            catch (Exception error)
            {
                MessageBox.Show("O CONDOR não conseguiu iniciar.\n\n" + error.Message,
                    "CONDOR", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        internal static bool NucleoPronto(int timeoutMs)
        {
            try
            {
                var pedido = (HttpWebRequest)WebRequest.Create(UiUrl);
                pedido.Timeout = timeoutMs;
                pedido.Proxy = null;
                using (var resposta = (HttpWebResponse)pedido.GetResponse())
                    return resposta.StatusCode == HttpStatusCode.OK;
            }
            catch
            {
                return false;
            }
        }
    }

    internal sealed class Carregando : Form
    {
        private readonly Timer relogio = new Timer { Interval = 400 };
        private readonly Label estado = new Label();
        private readonly DateTime inicio = DateTime.Now;
        private readonly string root;
        private DateTime? prontoEm;
        private DateTime atualizandoAte = DateTime.MinValue;
        private double tempoAtualizando;

        // O atualizador (condor/atualizador.py) escreve aqui o que está fazendo.
        private string LerAtualizacao()
        {
            try
            {
                string arquivo = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                    ".condor", "runtime", "atualizacao.txt");
                string texto = File.Exists(arquivo) ? File.ReadAllText(arquivo).Trim() : "";
                if (texto.Length > 0) tempoAtualizando += relogio.Interval / 1000.0;
                return texto;
            }
            catch
            {
                return "";
            }
        }

        internal Carregando(string root)
        {
            this.root = root;
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(340, 120);
            BackColor = Color.FromArgb(7, 9, 22);
            ShowInTaskbar = true;
            Text = "CONDOR";
            TopMost = true;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            var titulo = new Label
            {
                Text = "CONDOR", Font = new Font("Consolas", 20f, FontStyle.Bold),
                ForeColor = Color.FromArgb(94, 234, 212), AutoSize = true, Location = new Point(24, 22),
            };
            estado.Text = "iniciando o núcleo local...";
            estado.Font = new Font("Consolas", 9f);
            estado.ForeColor = Color.FromArgb(139, 124, 255);
            estado.AutoSize = true;
            estado.Location = new Point(27, 72);
            Controls.Add(titulo);
            Controls.Add(estado);
            Paint += (s, e) => e.Graphics.DrawRectangle(new Pen(Color.FromArgb(60, 94, 234, 212)), 0, 0, Width - 1, Height - 1);

            relogio.Tick += (s, e) => Verificar();
            relogio.Start();
        }

        private void Verificar()
        {
            double segundos = (DateTime.Now - inicio).TotalSeconds;
            if (prontoEm == null && CondorLauncher.NucleoPronto(300))
            {
                prontoEm = DateTime.Now;
                estado.Text = "abrindo a janela...";
            }
            // A janela nativa leva ~1-2 s para aparecer depois do núcleo.
            if (prontoEm != null && (DateTime.Now - prontoEm.Value).TotalSeconds > 2.5)
            {
                Close();
                return;
            }
            string atualizando = LerAtualizacao();
            if (prontoEm == null)
            {
                if (atualizando.Length > 0)
                {
                    estado.Text = atualizando;
                    atualizandoAte = DateTime.Now.AddSeconds(30);
                }
                else
                {
                    estado.Text = segundos < 15 ? "iniciando o núcleo local..." : "carregando o modelo de IA... (" + (int)segundos + " s)";
                }
            }
            // Atualização (download + bibliotecas) pode levar alguns minutos.
            if (segundos > 150 && DateTime.Now > atualizandoAte && segundos > 150 + tempoAtualizando)
            {
                relogio.Stop();
                Hide();
                MessageBox.Show(
                    "O CONDOR demorou demais para iniciar.\n\nVeja o registro em:\n" +
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".condor", "logs", "condor.log"),
                    "CONDOR", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                Close();
            }
        }
    }
}
