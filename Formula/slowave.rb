class Slowave < Formula
  include Language::Python::Virtualenv

  desc "Brain-inspired long-term memory for AI agents — zero LLM during ingest or retrieval"
  homepage "https://github.com/mrsalty/slowave"
  url "https://github.com/mrsalty/slowave/archive/refs/tags/v0.1.7.tar.gz"
  sha256 "a7843452d1fa738b88bcac2dc104f5a69ffc0c0f295f869c991e4cffeeab07a6"
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

  test do
    assert_match "Usage:", shell_output("#{bin}/slowave --help")
  end
end
