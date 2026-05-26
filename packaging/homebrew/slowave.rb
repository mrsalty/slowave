# Homebrew formula for Slowave.
#
# Reference copy. Canonical lives at:
#   github.com/mrsalty/homebrew-slowave/Formula/slowave.rb
#
# After each release, tag the commit (e.g. v0.2.0), push the tag, then:
#   curl -sL https://github.com/mrsalty/slowave/archive/refs/tags/vX.Y.Z.tar.gz \
#     | shasum -a 256
# Update `url` (version) and `sha256` in the tap formula and commit.

class Slowave < Formula
  include Language::Python::Virtualenv

  desc "Brain-inspired long-term memory for AI agents — zero LLM during ingest or retrieval"
  homepage "https://github.com/mrsalty/slowave"
  url "https://github.com/mrsalty/slowave/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "FILL_AFTER_TAG_PUSH"
  license "MIT"
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
