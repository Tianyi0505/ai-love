# Speech Runtime

Start the speech service with python -m gptsovits.gpt_sovits_service. GPTSoVITSService serves FastAPI HTTP and NATS requests through one SynthesisService.

## Synthesis results

- HTTP POST /synthesize and ai.speech.request use one request policy.
- The request policy validates ai_id and text length.
- synthesize() returns a playable audio reference.
- preview() returns a prepared synthesis result.
- Speech engines load through the ai_love.gptsovits entry-point group.
- Voice references stay within the owning ai_id scope.
- Output settings define the file name, directory, extension, and PCM duration.

service.gptsovits defines HTTP, request limits, engines, voices, and output settings. Deployment resources provide connection credentials.
