using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Management;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

// Instalador do CONDOR: leva o código embutido, instala numa pasta do usuário
// (sem administrador) e roda scripts\instalar_condor.ps1 mostrando o progresso.
// Memória, cofre e modelos ficam em ~/.condor e nunca são tocados.
namespace Condor.Windows
{
    internal sealed class CondorSetup : Form
    {
        private static readonly Color Fundo = Color.FromArgb(7, 9, 22);
        private static readonly Color Painel = Color.FromArgb(12, 15, 34);
        private static readonly Color Violeta = Color.FromArgb(139, 124, 255);
        private static readonly Color Ciano = Color.FromArgb(94, 234, 212);
        private static readonly Color Texto = Color.FromArgb(214, 222, 235);
        private static readonly Color Apagado = Color.FromArgb(120, 130, 155);

        private readonly TextBox pasta = new TextBox();
        private readonly CheckBox comImagem = new CheckBox();
        private readonly CheckBox segundoPlano = new CheckBox();
        private readonly Button instalar = new Button();
        private readonly Button escolher = new Button();
        private readonly ProgressBar progresso = new ProgressBar();
        private readonly Label etapa = new Label();
        private readonly TextBox log = new TextBox();
        private readonly string arquivoLog = Path.Combine(Path.GetTempPath(), "condor-setup.log");
        private bool concluido;
        private readonly bool automatico;

        // CondorSetup.exe /auto [/imagem] [/fundo] [/pasta=C:\...] instala sem cliques
        // (mostra o progresso e fecha sozinho ao terminar bem).
        [STAThread]
        private static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new CondorSetup(args));
        }

        private CondorSetup(string[] args)
        {
            automatico = Array.Exists(args, a => a.Equals("/auto", StringComparison.OrdinalIgnoreCase));
            Text = "Instalar CONDOR";
            ClientSize = new Size(620, 560);
            FormBorderStyle = FormBorderStyle.FixedSingle;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Fundo;
            ForeColor = Texto;
            Font = new Font("Segoe UI", 9.5f);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            var titulo = Rotulo("CONDOR", new Font("Consolas", 26f, FontStyle.Bold), Ciano, 28, 22);
            var subtitulo = Rotulo("Seu assistente pessoal, rodando neste PC.", Font, Apagado, 32, 70);

            var rotuloPasta = Rotulo("PASTA DO APLICATIVO", new Font("Consolas", 8f), Violeta, 32, 112);
            pasta.SetBounds(32, 132, 470, 26);
            pasta.BackColor = Painel; pasta.ForeColor = Texto; pasta.BorderStyle = BorderStyle.FixedSingle;
            pasta.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Condor");
            Botao(escolher, "...", 510, 131, 78, 27, false);
            escolher.Click += (s, e) =>
            {
                using (var dialogo = new FolderBrowserDialog { SelectedPath = pasta.Text })
                    if (dialogo.ShowDialog(this) == DialogResult.OK) pasta.Text = Path.Combine(dialogo.SelectedPath, "Condor");
            };

            string modelosImagem = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".condor", "models", "image");
            Opcao(comImagem, "Criação de imagem local (baixa ~7 GB se ainda não existir)", 32, 176,
                Directory.Exists(modelosImagem) && Directory.GetFiles(modelosImagem, "*.gguf").Length > 0);
            Opcao(segundoPlano, "Deixar o CONDOR ouvindo \"Condor\" em segundo plano ao ligar o PC\n(nenhuma janela abre sozinha)", 32, 206, true);
            segundoPlano.Height = 40;

            Botao(instalar, "INSTALAR", 32, 262, 556, 40, true);
            instalar.Click += (s, e) => { if (concluido) Abrir(); else Iniciar(); };

            progresso.SetBounds(32, 318, 556, 8);
            progresso.Maximum = 100;
            etapa.SetBounds(32, 334, 556, 20);
            etapa.ForeColor = Ciano; etapa.Font = new Font("Consolas", 8.5f);
            etapa.Text = "Memória, cofre e modelos em ~/.condor são preservados.";

            log.SetBounds(32, 362, 556, 170);
            log.Multiline = true; log.ReadOnly = true; log.ScrollBars = ScrollBars.Vertical;
            log.BackColor = Painel; log.ForeColor = Apagado; log.BorderStyle = BorderStyle.None;
            log.Font = new Font("Consolas", 8f);

            Controls.AddRange(new Control[] { titulo, subtitulo, rotuloPasta, pasta, escolher, comImagem, segundoPlano, instalar, progresso, etapa, log });

            if (automatico)
            {
                comImagem.Checked = Array.Exists(args, a => a.Equals("/imagem", StringComparison.OrdinalIgnoreCase));
                segundoPlano.Checked = Array.Exists(args, a => a.Equals("/fundo", StringComparison.OrdinalIgnoreCase));
                string destinoArg = Array.Find(args, a => a.StartsWith("/pasta=", StringComparison.OrdinalIgnoreCase));
                if (destinoArg != null) pasta.Text = destinoArg.Substring(7).Trim('"');
                Shown += (s, e) => Iniciar();
            }
        }

        private static Label Rotulo(string texto, Font fonte, Color cor, int x, int y)
        {
            return new Label { Text = texto, Font = fonte, ForeColor = cor, AutoSize = true, Location = new Point(x, y), BackColor = Color.Transparent };
        }

        private void Opcao(CheckBox caixa, string texto, int x, int y, bool marcado)
        {
            caixa.Text = texto; caixa.Checked = marcado; caixa.ForeColor = Texto;
            caixa.SetBounds(x, y, 556, 24); caixa.FlatStyle = FlatStyle.Flat;
        }

        private static void Botao(Button botao, string texto, int x, int y, int w, int h, bool principal)
        {
            botao.Text = texto; botao.SetBounds(x, y, w, h);
            botao.FlatStyle = FlatStyle.Flat; botao.Cursor = Cursors.Hand;
            botao.FlatAppearance.BorderColor = principal ? Ciano : Violeta;
            botao.BackColor = principal ? Color.FromArgb(10, 40, 44) : Painel;
            botao.ForeColor = principal ? Ciano : Texto;
            botao.Font = new Font("Consolas", principal ? 11f : 9f, FontStyle.Bold);
        }

        private void Escrever(string linha)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(Escrever), linha); return; }
            File.AppendAllText(arquivoLog, linha + Environment.NewLine, Encoding.UTF8);
            var passo = Regex.Match(linha, @"^##CONDOR-PASSO (\d+)/(\d+) (.*)$");
            if (passo.Success)
            {
                int n = int.Parse(passo.Groups[1].Value), total = int.Parse(passo.Groups[2].Value);
                // Passo 0 (fechar o CONDOR aberto) daria -2: a barra só aceita 0..100.
                progresso.Value = Math.Max(0, Math.Min(99, 8 + (n - 1) * 90 / total));
                etapa.Text = "[" + n + "/" + total + "] " + passo.Groups[3].Value;
                return;
            }
            if (linha == "##CONDOR-PRONTO") return;
            log.AppendText(linha + Environment.NewLine);
        }

        private void Iniciar()
        {
            string destino = pasta.Text.Trim();
            string motivo = PastaInsegura(destino);
            if (motivo != null)
            {
                MessageBox.Show(this, motivo, "CONDOR", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                if (automatico) { Environment.ExitCode = 2; Close(); }
                return;
            }
            foreach (Control c in new Control[] { pasta, escolher, comImagem, segundoPlano, instalar }) c.Enabled = false;
            instalar.Text = "INSTALANDO...";
            File.WriteAllText(arquivoLog, "CONDOR setup " + DateTime.Now + Environment.NewLine);
            bool imagem = comImagem.Checked, fundo = segundoPlano.Checked;
            new Thread(() => Instalar(destino, imagem, fundo)) { IsBackground = true }.Start();
        }

        // O desinstalador apaga a pasta do app inteira. Por isso ela precisa ser
        // só do CONDOR: nunca a pasta do usuário, a raiz de um disco, algo que
        // contenha ~/.condor ou uma pasta já usada por outra coisa.
        private static string PastaInsegura(string destino)
        {
            if (destino.Length < 4 || !Path.IsPathRooted(destino)) return "Escolha uma pasta válida.";
            string alvo;
            char barra = Path.DirectorySeparatorChar;
            try { alvo = Path.GetFullPath(destino).TrimEnd(barra) + barra; } catch { return "Escolha uma pasta válida."; }
            string perfil = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile).TrimEnd(barra) + barra;
            string estado = Path.Combine(perfil, ".condor") + barra;
            if (alvo.Length <= 4) return "A raiz de um disco não pode ser a pasta do CONDOR.";
            if (perfil.StartsWith(alvo, StringComparison.OrdinalIgnoreCase) || estado.StartsWith(alvo, StringComparison.OrdinalIgnoreCase)
                || alvo.StartsWith(estado, StringComparison.OrdinalIgnoreCase))
                return "Essa pasta contém seus dados pessoais (ou a memória do CONDOR). Escolha uma pasta só para o aplicativo.";
            if (string.Equals(alvo, perfil, StringComparison.OrdinalIgnoreCase)) return "Escolha uma subpasta, não a sua pasta de usuário.";
            if (Directory.Exists(alvo) && Directory.EnumerateFileSystemEntries(alvo).GetEnumerator().MoveNext()
                && !File.Exists(Path.Combine(alvo, ".condor-instalado")))
                return "Essa pasta já tem outros arquivos. Escolha uma pasta vazia ou a do CONDOR já instalado.";
            return null;
        }

        private void Instalar(string destino, bool imagem, bool fundo)
        {
            int codigo = -1;
            try
            {
                Escrever("##CONDOR-PASSO 0/9 Fechando o CONDOR que estiver aberto");
                FecharCondorAberto();
                Escrever("Copiando o aplicativo para " + destino);
                Extrair(destino);
                File.WriteAllText(Path.Combine(destino, ".condor-instalado"), DateTime.Now.ToString("o"));

                string script = Path.Combine(destino, "scripts", "instalar_condor.ps1");
                var inicio = new ProcessStartInfo
                {
                    FileName = Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe"),
                    Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"" + script + "\"" +
                                (imagem ? " -ComImagem" : "") + (fundo ? " -SegundoPlano" : ""),
                    WorkingDirectory = destino,
                    UseShellExecute = false, CreateNoWindow = true,
                    RedirectStandardOutput = true, RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
                };
                inicio.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                inicio.EnvironmentVariables["PIP_NO_INPUT"] = "1";
                using (var processo = Process.Start(inicio))
                {
                    processo.OutputDataReceived += (s, e) => { if (e.Data != null) Escrever(e.Data); };
                    processo.ErrorDataReceived += (s, e) => { if (e.Data != null) Escrever(e.Data); };
                    processo.BeginOutputReadLine();
                    processo.BeginErrorReadLine();
                    processo.WaitForExit();
                    codigo = processo.ExitCode;
                }
            }
            catch (Exception erro)
            {
                Escrever("ERRO: " + erro.Message);
            }
            BeginInvoke(new Action(() => Terminar(destino, codigo == 0)));
        }

        private void Terminar(string destino, bool ok)
        {
            pasta.Tag = destino;
            if (ok)
            {
                progresso.Value = 100;
                etapa.Text = "PRONTO. O CONDOR está no Menu Iniciar e na Área de Trabalho.";
                instalar.Text = "ABRIR O CONDOR";
                concluido = true;
                instalar.Enabled = true;
                if (automatico) { Environment.ExitCode = 0; Close(); }
            }
            else
            {
                etapa.ForeColor = Color.FromArgb(244, 114, 182);
                etapa.Text = "A instalação parou. Log completo: " + arquivoLog;
                instalar.Text = "TENTAR DE NOVO";
                if (automatico) { Environment.ExitCode = 1; Close(); }
                foreach (Control c in new Control[] { pasta, escolher, comImagem, segundoPlano, instalar }) c.Enabled = true;
            }
        }

        private void Abrir()
        {
            string exe = Path.Combine((string)pasta.Tag, "Condor.exe");
            if (File.Exists(exe)) Process.Start(new ProcessStartInfo(exe) { WorkingDirectory = (string)pasta.Tag });
            Close();
        }

        // Um CONDOR aberto (de qualquer pasta) segura as portas 7777 e 11434 e
        // os arquivos do app. Fecha núcleo, janela e o Ollama dele; os dados
        // ficam gravados porque a memória persiste a cada mudança.
        private void FecharCondorAberto()
        {
            string[] marcas = { "condor_background.pyw", "condor_window.pyw", "condor_app.pyw", "-m condor", @"\scripts\run.ps1", @"\runtime\ollama\windows\" };
            using (var busca = new ManagementObjectSearcher("SELECT ProcessId, CommandLine, ExecutablePath FROM Win32_Process"))
            {
                foreach (ManagementObject item in busca.Get())
                {
                    string linha = ((item["CommandLine"] as string) ?? "") + " " + ((item["ExecutablePath"] as string) ?? "");
                    bool doCondor = linha.IndexOf("condor", StringComparison.OrdinalIgnoreCase) >= 0;
                    foreach (string marca in marcas)
                    {
                        if (!doCondor || linha.IndexOf(marca, StringComparison.OrdinalIgnoreCase) < 0) continue;
                        try
                        {
                            int pid = Convert.ToInt32(item["ProcessId"]);
                            if (pid == Process.GetCurrentProcess().Id) break;
                            Process.GetProcessById(pid).Kill();
                            Escrever("Fechado: " + linha.Trim().Substring(0, Math.Min(110, linha.Trim().Length)));
                        }
                        catch { }
                        break;
                    }
                }
            }
            Thread.Sleep(1500);
        }

        private void Extrair(string destino)
        {
            Directory.CreateDirectory(destino);
            string raiz = Path.GetFullPath(destino).TrimEnd('\\') + "\\";
            using (Stream pacote = Assembly.GetExecutingAssembly().GetManifestResourceStream("CondorPayload"))
            {
                if (pacote == null) throw new InvalidOperationException("instalador sem o pacote do CONDOR");
                using (var zip = new ZipArchive(pacote, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entrada in zip.Entries)
                    {
                        string alvo = Path.GetFullPath(Path.Combine(destino, entrada.FullName));
                        if (!alvo.StartsWith(raiz, StringComparison.OrdinalIgnoreCase)) continue; // nada fora da pasta
                        if (entrada.FullName.EndsWith("/")) { Directory.CreateDirectory(alvo); continue; }
                        Directory.CreateDirectory(Path.GetDirectoryName(alvo));
                        entrada.ExtractToFile(alvo, true);
                    }
                }
            }
        }
    }
}
