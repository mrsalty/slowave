class Slowave < Formula
  include Language::Python::Virtualenv

  desc "Brain-inspired long-term memory for AI agents — zero LLM during ingest or retrieval"
  homepage "https://github.com/mrsalty/slowave"
  url "https://files.pythonhosted.org/packages/source/s/slowave/slowave-0.12.0.tar.gz"
  sha256 "676edb1523685a7e468c1f3f9cbcfcab10161f5fd49e86b0d05b364d0f37a406"
  license "AGPL-3.0-or-later"
  head "https://github.com/mrsalty/slowave.git", branch: "main"

  depends_on "python@3.12"

  def install
    virtualenv_create(libexec, "python3.12")
    system "python3.12", "-m", "pip", "--python=#{libexec}/bin/python",
           "install", "-v", "--prefer-binary", "--ignore-installed", buildpath
    bin.install_symlink libexec/"bin/slowave"
    bin.install_symlink libexec/"bin/slowave-mcp"
  end

  def post_install
    system bin/"slowave", "setup"
  rescue => e
    opoo "Slowave post-install setup failed: #{e}. Run `slowave setup` manually."
  end

  test do
    assert_match "Usage:", shell_output("#{bin}/slowave --help")
  end
end
